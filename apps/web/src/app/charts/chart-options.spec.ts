import { CHART_THEMES } from './chart-theme';
import { RangePoint, rangeOption, trendOption } from './chart-options';

const theme = CHART_THEMES.light;
const text = { description: 'Speed over the last 5 minutes', unit: 'kn', decimals: 1 };

interface Series {
  name: string;
  data: [number, number][];
  lineStyle?: { width?: number };
}
const seriesOf = (option: Record<string, unknown>) => option['series'] as Series[];

describe('trendOption', () => {
  it('draws one 2px line on a single y-axis, without a legend', () => {
    const option = trendOption(
      [
        [1000, 7.5],
        [2000, 8],
      ],
      theme,
      text,
      [0, 5000],
    );

    const series = seriesOf(option);
    expect(series).toHaveLength(1);
    expect(series[0].data).toEqual([
      [1000, 7.5],
      [2000, 8],
    ]);
    expect(series[0].lineStyle?.width).toBe(2);
    expect(option['legend']).toBeUndefined();
    expect(Array.isArray(option['yAxis'])).toBe(false);
  });

  it('shows the whole requested time range, even where data is missing', () => {
    const xAxis = trendOption([[4000, 1]], theme, text, [0, 5000])['xAxis'];

    expect(xAxis).toMatchObject({ type: 'time', min: 0, max: 5000 });
  });

  it('describes the chart for screen readers', () => {
    const option = trendOption([], theme, text, [0, 1000]);

    expect(option['aria']).toEqual({ enabled: true, label: { description: text.description } });
  });
});

describe('rangeOption', () => {
  const points: RangePoint[] = [
    [1000, 5, 4, 6],
    [2000, 10, 9, 12],
  ];

  it('stacks a min-max band behind the average line', () => {
    const [min, range, average] = seriesOf(rangeOption(points, theme, text, [0, 3000]));

    expect(min.data).toEqual([
      [1000, 4],
      [2000, 9],
    ]);
    // The band is drawn as "max - min" stacked on top of the minimum.
    expect(range.data).toEqual([
      [1000, 2],
      [2000, 3],
    ]);
    expect(average.data).toEqual([
      [1000, 5],
      [2000, 10],
    ]);
  });

  it('shows average and range in the tooltip, not the stacked helper values', () => {
    const option = rangeOption(points, theme, text, [0, 3000]);
    const formatter = (option['tooltip'] as { formatter: (p: unknown) => string }).formatter;

    const html = formatter([{ dataIndex: 1 }]);

    expect(html).toContain('10.0 kn</strong> average');
    expect(html).toContain('9.0 kn – 12.0 kn range');
  });
});
