#!/usr/bin/env python3
"""
IPC (Inter-Process Communication) Integration Tests

Tests shared memory communication between C controller and Python API.

Prerequisites:
  - Controller service running (for full tests)
  - POSIX IPC support available

Run with:
  pytest tests/integration/test_ipc.py -v
"""

import os
import pytest
import struct
import time
from unittest.mock import patch, MagicMock

# Try to import posix_ipc, skip tests if not available
try:
    import posix_ipc
    HAS_POSIX_IPC = True
except ImportError:
    HAS_POSIX_IPC = False
    posix_ipc = None

# IPC configuration
SHM_NAME = "/wtc_shared_memory"
SEM_NAME = "/wtc_semaphore"
MQ_NAME = "/wtc_message_queue"


@pytest.mark.skipif(not HAS_POSIX_IPC, reason="posix_ipc not available")
class TestIPCSharedMemory:
    """Test shared memory operations."""

    def test_shm_creation(self):
        """Verify shared memory segment creation."""
        try:
            # Try to create or open shared memory
            shm = posix_ipc.SharedMemory(
                SHM_NAME,
                flags=posix_ipc.O_CREAT,
                size=4096
            )
            assert shm.size >= 4096
            shm.close_fd()

            # Clean up
            shm.unlink()
        except posix_ipc.ExistentialError:
            # Already exists from controller - that's OK
            shm = posix_ipc.SharedMemory(SHM_NAME)
            assert shm.size > 0
            shm.close_fd()
        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")

    def test_shm_read_write(self):
        """Test reading/writing to shared memory."""
        try:
            # Create test shared memory
            test_shm_name = "/wtc_test_shm"
            shm = posix_ipc.SharedMemory(
                test_shm_name,
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                size=1024
            )

            import mmap
            mm = mmap.mmap(shm.fd, shm.size)

            # Write test data
            test_data = b"Hello IPC Test"
            mm.write(test_data)

            # Read back
            mm.seek(0)
            read_data = mm.read(len(test_data))

            assert read_data == test_data

            # Clean up
            mm.close()
            shm.close_fd()
            shm.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")

    def test_shm_concurrent_access(self):
        """Test concurrent access from multiple processes."""
        try:
            import multiprocessing
            import mmap

            test_shm_name = "/wtc_concurrent_test"
            shm = posix_ipc.SharedMemory(
                test_shm_name,
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                size=1024
            )

            sem = posix_ipc.Semaphore(
                "/wtc_test_sem",
                flags=posix_ipc.O_CREAT,
                initial_value=1
            )

            def writer_process(count):
                """Write count to shared memory."""
                shm = posix_ipc.SharedMemory(test_shm_name)
                sem = posix_ipc.Semaphore("/wtc_test_sem")
                mm = mmap.mmap(shm.fd, shm.size)

                for i in range(count):
                    sem.acquire()
                    mm.seek(0)
                    current = struct.unpack('i', mm.read(4))[0]
                    mm.seek(0)
                    mm.write(struct.pack('i', current + 1))
                    sem.release()

                mm.close()
                shm.close_fd()

            # Initialize counter
            mm = mmap.mmap(shm.fd, shm.size)
            mm.write(struct.pack('i', 0))
            mm.close()

            # Run concurrent writers
            processes = []
            for _ in range(2):
                p = multiprocessing.Process(target=writer_process, args=(10,))
                processes.append(p)
                p.start()

            for p in processes:
                p.join()

            # Read final value
            mm = mmap.mmap(shm.fd, shm.size)
            mm.seek(0)
            final_value = struct.unpack('i', mm.read(4))[0]
            mm.close()

            assert final_value == 20, f"Expected 20, got {final_value}"

            # Clean up
            sem.unlink()
            shm.close_fd()
            shm.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")

    def test_shm_cleanup_on_exit(self):
        """Verify proper cleanup of shared memory."""
        test_shm_name = "/wtc_cleanup_test"

        try:
            # Create shared memory
            shm = posix_ipc.SharedMemory(
                test_shm_name,
                flags=posix_ipc.O_CREAT,
                size=1024
            )
            shm.close_fd()

            # Unlink it
            shm.unlink()

            # Verify it's gone
            with pytest.raises(posix_ipc.ExistentialError):
                posix_ipc.SharedMemory(test_shm_name)

        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")


@pytest.mark.skipif(not HAS_POSIX_IPC, reason="posix_ipc not available")
class TestIPCSemaphores:
    """Test semaphore synchronization."""

    def test_semaphore_acquisition(self):
        """Test acquiring semaphore lock."""
        try:
            sem = posix_ipc.Semaphore(
                "/wtc_sem_test",
                flags=posix_ipc.O_CREAT,
                initial_value=1
            )

            # Acquire and release
            sem.acquire()
            assert True  # If we got here, acquisition worked
            sem.release()

            # Clean up
            sem.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for semaphore")

    def test_semaphore_timeout(self):
        """Test semaphore acquisition timeout."""
        try:
            sem = posix_ipc.Semaphore(
                "/wtc_sem_timeout",
                flags=posix_ipc.O_CREAT,
                initial_value=0  # Start locked
            )

            start = time.time()
            try:
                # This should timeout
                sem.acquire(timeout=0.5)
                pytest.fail("Should have timed out")
            except posix_ipc.BusyError:
                elapsed = time.time() - start
                assert 0.4 < elapsed < 1.0, f"Timeout was {elapsed}s"

            # Clean up
            sem.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for semaphore")

    def test_semaphore_release(self):
        """Test proper semaphore release."""
        try:
            sem = posix_ipc.Semaphore(
                "/wtc_sem_release",
                flags=posix_ipc.O_CREAT,
                initial_value=1
            )

            # Acquire twice (with release in between)
            sem.acquire()
            sem.release()
            sem.acquire()  # Should not block
            sem.release()

            # Clean up
            sem.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for semaphore")


@pytest.mark.skipif(not HAS_POSIX_IPC, reason="posix_ipc not available")
class TestIPCMessageQueue:
    """Test message queue operations."""

    def test_message_send_receive(self):
        """Test sending and receiving messages."""
        try:
            mq = posix_ipc.MessageQueue(
                "/wtc_mq_test",
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                max_messages=10,
                max_message_size=256
            )

            # Send message
            test_message = b"Test message"
            mq.send(test_message)

            # Receive message
            received, priority = mq.receive()
            assert received == test_message

            # Clean up
            mq.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for message queue")

    def test_message_queue_overflow(self):
        """Test behavior when queue is full."""
        try:
            mq = posix_ipc.MessageQueue(
                "/wtc_mq_overflow",
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                max_messages=2,
                max_message_size=256
            )

            # Fill queue
            mq.send(b"Message 1")
            mq.send(b"Message 2")

            # Third message should block/fail with non-blocking
            try:
                # Set non-blocking
                import fcntl
                mq.block = False
                mq.send(b"Message 3")
                pytest.fail("Should have raised error")
            except posix_ipc.BusyError:
                pass  # Expected

            # Drain queue
            mq.receive()
            mq.receive()

            # Clean up
            mq.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for message queue")


class TestIPCControllerIntegration:
    """Test IPC integration with running controller."""

    @pytest.fixture(autouse=True)
    def check_controller(self):
        """Check if controller is running."""
        # This would check if the actual controller is running
        # For now, skip these tests in CI
        if os.environ.get("CI"):
            pytest.skip("Controller not available in CI")

    @pytest.mark.skip(reason="Requires running controller")
    def test_controller_shm_exists(self):
        """Verify controller creates shared memory."""
        try:
            shm = posix_ipc.SharedMemory(SHM_NAME)
            assert shm.size > 0
            shm.close_fd()
        except posix_ipc.ExistentialError:
            pytest.fail("Controller shared memory not found")

    @pytest.mark.skip(reason="Requires running controller")
    def test_read_controller_state(self):
        """Read controller state from shared memory."""
        try:
            import mmap
            shm = posix_ipc.SharedMemory(SHM_NAME)
            mm = mmap.mmap(shm.fd, shm.size, access=mmap.ACCESS_READ)

            # Read first 4 bytes as status
            status = struct.unpack('I', mm.read(4))[0]
            assert status in [0, 1, 2]  # IDLE, RUNNING, ERROR

            mm.close()
            shm.close_fd()

        except posix_ipc.ExistentialError:
            pytest.skip("Controller not running")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
