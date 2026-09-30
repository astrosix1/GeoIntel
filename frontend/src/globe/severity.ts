export function colorForSeverity(severity: number): string {
  if (severity >= 80) return '#dc2626'; // red - critical
  if (severity >= 50) return '#f97316'; // orange - high
  if (severity >= 20) return '#eab308'; // yellow - moderate
  return '#22c55e'; // green - low
}

export function labelForSeverity(severity: number): string {
  if (severity >= 80) return 'Critical';
  if (severity >= 50) return 'High';
  if (severity >= 20) return 'Moderate';
  return 'Low';
}
