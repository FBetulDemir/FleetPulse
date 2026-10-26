import type { EChartsCoreOption } from 'echarts/core';

import { ChartTheme } from './chart-theme';

/** [time in ms, value] */
export type TimePoint = [number, number];

/** [time in ms, average, min, max] */
export type RangePoint = [number, number, number, number];

export interface ChartText {
  /** Read by screen readers, e.g. "Speed over the last 5 minutes". */
  description: string;
  unit: string;
  decimals: number;
}

/**
 * [start, end] in ms. The x-axis always shows the whole range the chart claims to show,
 * so missing data looks missing instead of being stretched across the chart.
 */
export type TimeRange = [number, number];

const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

function baseOption(theme: ChartTheme, text: ChartText, range: TimeRange): EChartsCoreOption {
  return {
    animation: false,
    aria: { enabled: true, label: { description: text.description } },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    xAxis: {
      type: 'time',
      min: range[0],
      max: range[1],
      axisLine: { lineStyle: { color: theme.axis } },
      axisTick: { show: false },
      axisLabel: { color: theme.text, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      // Fit the data instead of always starting at zero: small changes stay visible.
      scale: true,
      axisLabel: { color: theme.text },
      splitLine: { lineStyle: { color: theme.gridline, width: 1, type: 'solid' } },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: theme.axis, width: 1 } },
      backgroundColor: theme.tooltipBackground,
      borderColor: theme.gridline,
      textStyle: { color: theme.textStrong },
    },
  };
}

const line = (theme: ChartTheme) => ({
  type: 'line',
  showSymbol: false,
  lineStyle: { width: 2, color: theme.series, cap: 'round', join: 'round' },
  itemStyle: { color: theme.series },
  emphasis: { disabled: true },
});

/** One metric over time, e.g. the last few minutes of live speed. */
export function trendOption(
  points: readonly TimePoint[],
  theme: ChartTheme,
  text: ChartText,
  range: TimeRange,
): EChartsCoreOption {
  const format = (value: unknown) => `${Number(value).toFixed(text.decimals)} ${text.unit}`;
  const base = baseOption(theme, text, range);
  return {
    ...base,
    tooltip: { ...(base['tooltip'] as object), valueFormatter: format },
    series: [{ ...line(theme), name: text.description, data: points }],
  };
}

/**
 * Average as a line, with the min-max range as a band behind it.
 * The band is drawn ECharts' usual way: an invisible "min" line, and a "max - min"
 * area stacked on top of it.
 */
export function rangeOption(
  points: readonly RangePoint[],
  theme: ChartTheme,
  text: ChartText,
  range: TimeRange,
): EChartsCoreOption {
  const fixed = (value: number) => `${value.toFixed(text.decimals)} ${text.unit}`;
  const base = baseOption(theme, text, range);
  return {
    ...base,
    tooltip: {
      ...(base['tooltip'] as object),
      // Built from numbers and a formatted time only, never from user-provided text.
      formatter: (params: { dataIndex: number }[]) => {
        const point = points[params[0]?.dataIndex ?? -1];
        if (!point) return '';
        const [time, avg, min, max] = point;
        return (
          `<strong>${fixed(avg)}</strong> average<br>` +
          `${fixed(min)} – ${fixed(max)} range<br>` +
          `<span style="color:${theme.text}">${timeFormat.format(time)}</span>`
        );
      },
    },
    series: [
      {
        type: 'line',
        name: 'Minimum',
        stack: 'range',
        data: points.map(([time, , min]) => [time, min]),
        lineStyle: { opacity: 0 },
        showSymbol: false,
        emphasis: { disabled: true },
      },
      {
        type: 'line',
        name: 'Range',
        stack: 'range',
        data: points.map(([time, , min, max]) => [time, max - min]),
        lineStyle: { opacity: 0 },
        areaStyle: { color: theme.band },
        showSymbol: false,
        emphasis: { disabled: true },
      },
      { ...line(theme), name: 'Average', data: points.map(([time, avg]) => [time, avg]) },
    ],
  };
}
