/**
 * Export utilities for SCADA HMI data
 */

import { QUALITY_CODES, getQualityLabel } from '@/constants/quality';

export interface ExportOptions {
  filename?: string;
  includeHeaders?: boolean;
  dateFormat?: 'iso' | 'locale' | 'unix';
}

export interface TrendExportData {
  tagId: number;
  tagName: string;
  samples: {
    timestamp: string;
    value: number;
    quality: number;
  }[];
}

/**
 * Format a date based on the specified format
 */
function formatDate(date: Date | string, format: ExportOptions['dateFormat'] = 'iso'): string {
  const d = new Date(date);
  switch (format) {
    case 'locale':
      return d.toLocaleString();
    case 'unix':
      return String(Math.floor(d.getTime() / 1000));
    case 'iso':
    default:
      return d.toISOString();
  }
}

/**
 * Quality code to text mapping using OPC UA quality codes
 */
function qualityToText(quality: number): string {
  // Use bitmask to get quality category (top 2 bits)
  const category = quality & 0xC0;
  if (category === QUALITY_CODES.GOOD) return 'GOOD';
  if (category === QUALITY_CODES.UNCERTAIN) return 'UNCERTAIN';
  if (category === QUALITY_CODES.BAD) return 'BAD';
  if (category === QUALITY_CODES.NOT_CONNECTED) return 'NOT_CONNECTED';
  return getQualityLabel(quality).toUpperCase();
}

/**
 * Export trend data to CSV format
 */
export function exportTrendToCSV(
  data: TrendExportData[],
  options: ExportOptions = {}
): void {
  const {
    filename = `trend_export_${new Date().toISOString().split('T')[0]}`,
    includeHeaders = true,
    dateFormat = 'iso',
  } = options;

  // Build CSV content
  const rows: string[][] = [];

  // Headers
  if (includeHeaders) {
    rows.push(['Timestamp', 'Tag Name', 'Tag ID', 'Value', 'Quality', 'Quality Code']);
  }

  // Data rows
  data.forEach(({ tagId, tagName, samples }) => {
    samples.forEach((sample) => {
      rows.push([
        formatDate(sample.timestamp, dateFormat),
        tagName,
        String(tagId),
        sample.value.toFixed(6),
        qualityToText(sample.quality),
        String(sample.quality),
      ]);
    });
  });

  // Convert to CSV string
  const csvContent = rows
    .map((row) =>
      row
        .map((cell) => {
          // Escape quotes and wrap in quotes if contains comma, quote, or newline
          if (cell.includes(',') || cell.includes('"') || cell.includes('\n')) {
            return `"${cell.replace(/"/g, '""')}"`;
          }
          return cell;
        })
        .join(',')
    )
    .join('\n');

  downloadFile(csvContent, `${filename}.csv`, 'text/csv;charset=utf-8;');
}

/**
 * Export trend data to JSON format
 */
export function exportTrendToJSON(
  data: TrendExportData[],
  options: ExportOptions = {}
): void {
  const { filename = `trend_export_${new Date().toISOString().split('T')[0]}` } = options;

  const exportData = {
    exportedAt: new Date().toISOString(),
    tags: data.map(({ tagId, tagName, samples }) => ({
      tagId,
      tagName,
      sampleCount: samples.length,
      timeRange: {
        start: samples[0]?.timestamp || null,
        end: samples[samples.length - 1]?.timestamp || null,
      },
      samples: samples.map((sample) => ({
        ...sample,
        qualityText: qualityToText(sample.quality),
      })),
    })),
  };

  const jsonContent = JSON.stringify(exportData, null, 2);
  downloadFile(jsonContent, `${filename}.json`, 'application/json');
}

/**
 * Export trend data to Excel-compatible XML (SpreadsheetML)
 */
export function exportTrendToExcel(
  data: TrendExportData[],
  options: ExportOptions = {}
): void {
  const {
    filename = `trend_export_${new Date().toISOString().split('T')[0]}`,
    dateFormat = 'locale',
  } = options;

  // Build SpreadsheetML
  let xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Styles>
    <Style ss:ID="Header">
      <Font ss:Bold="1"/>
      <Interior ss:Color="#4472C4" ss:Pattern="Solid"/>
      <Font ss:Color="#FFFFFF"/>
    </Style>
    <Style ss:ID="Good">
      <Interior ss:Color="#C6EFCE" ss:Pattern="Solid"/>
    </Style>
    <Style ss:ID="Uncertain">
      <Interior ss:Color="#FFEB9C" ss:Pattern="Solid"/>
    </Style>
    <Style ss:ID="Bad">
      <Interior ss:Color="#FFC7CE" ss:Pattern="Solid"/>
    </Style>
  </Styles>
`;

  // Create a worksheet for each tag
  data.forEach(({ tagId, tagName, samples }) => {
    const safeName = tagName.replace(/[^\w\s]/g, '').substring(0, 31);

    xml += `  <Worksheet ss:Name="${escapeXml(safeName)}">
    <Table>
      <Column ss:Width="150"/>
      <Column ss:Width="100"/>
      <Column ss:Width="80"/>
      <Row>
        <Cell ss:StyleID="Header"><Data ss:Type="String">Timestamp</Data></Cell>
        <Cell ss:StyleID="Header"><Data ss:Type="String">Value</Data></Cell>
        <Cell ss:StyleID="Header"><Data ss:Type="String">Quality</Data></Cell>
      </Row>
`;

    samples.forEach((sample) => {
      const quality = qualityToText(sample.quality);
      const styleId = quality === 'GOOD' ? 'Good' : quality === 'UNCERTAIN' ? 'Uncertain' : 'Bad';

      xml += `      <Row>
        <Cell><Data ss:Type="String">${escapeXml(formatDate(sample.timestamp, dateFormat))}</Data></Cell>
        <Cell><Data ss:Type="Number">${sample.value}</Data></Cell>
        <Cell ss:StyleID="${styleId}"><Data ss:Type="String">${quality}</Data></Cell>
      </Row>
`;
    });

    xml += `    </Table>
  </Worksheet>
`;
  });

  // Summary worksheet
  xml += `  <Worksheet ss:Name="Summary">
    <Table>
      <Column ss:Width="150"/>
      <Column ss:Width="100"/>
      <Column ss:Width="150"/>
      <Column ss:Width="150"/>
      <Row>
        <Cell ss:StyleID="Header"><Data ss:Type="String">Tag Name</Data></Cell>
        <Cell ss:StyleID="Header"><Data ss:Type="String">Samples</Data></Cell>
        <Cell ss:StyleID="Header"><Data ss:Type="String">Start Time</Data></Cell>
        <Cell ss:StyleID="Header"><Data ss:Type="String">End Time</Data></Cell>
      </Row>
`;

  data.forEach(({ tagName, samples }) => {
    xml += `      <Row>
        <Cell><Data ss:Type="String">${escapeXml(tagName)}</Data></Cell>
        <Cell><Data ss:Type="Number">${samples.length}</Data></Cell>
        <Cell><Data ss:Type="String">${escapeXml(samples[0]?.timestamp ? formatDate(samples[0].timestamp, dateFormat) : 'N/A')}</Data></Cell>
        <Cell><Data ss:Type="String">${escapeXml(samples[samples.length - 1]?.timestamp ? formatDate(samples[samples.length - 1].timestamp, dateFormat) : 'N/A')}</Data></Cell>
      </Row>
`;
  });

  xml += `    </Table>
  </Worksheet>
</Workbook>`;

  downloadFile(xml, `${filename}.xls`, 'application/vnd.ms-excel');
}

/**
 * Escape XML special characters
 */
function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * Download a file in the browser
 */
function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}

/**
 * Export alarm data to CSV
 */
export interface AlarmExportData {
  alarm_id: number;
  tag_name: string;
  severity: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  cleared: boolean;
  cleared_at?: string;
}

export function exportAlarmsToCSV(
  alarms: AlarmExportData[],
  options: ExportOptions = {}
): void {
  const {
    filename = `alarms_export_${new Date().toISOString().split('T')[0]}`,
    includeHeaders = true,
    dateFormat = 'iso',
  } = options;

  const rows: string[][] = [];

  if (includeHeaders) {
    rows.push([
      'Alarm ID',
      'Tag Name',
      'Severity',
      'Message',
      'Timestamp',
      'Acknowledged',
      'Acknowledged By',
      'Acknowledged At',
      'Cleared',
      'Cleared At',
    ]);
  }

  alarms.forEach((alarm) => {
    rows.push([
      String(alarm.alarm_id),
      alarm.tag_name,
      alarm.severity,
      alarm.message,
      formatDate(alarm.timestamp, dateFormat),
      alarm.acknowledged ? 'Yes' : 'No',
      alarm.acknowledged_by || '',
      alarm.acknowledged_at ? formatDate(alarm.acknowledged_at, dateFormat) : '',
      alarm.cleared ? 'Yes' : 'No',
      alarm.cleared_at ? formatDate(alarm.cleared_at, dateFormat) : '',
    ]);
  });

  const csvContent = rows
    .map((row) =>
      row
        .map((cell) => {
          if (cell.includes(',') || cell.includes('"') || cell.includes('\n')) {
            return `"${cell.replace(/"/g, '""')}"`;
          }
          return cell;
        })
        .join(',')
    )
    .join('\n');

  downloadFile(csvContent, `${filename}.csv`, 'text/csv;charset=utf-8;');
}
