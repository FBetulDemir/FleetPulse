import { Scheme } from './color-scheme';

/**
 * Chart colors per scheme. Canvas charts cannot read CSS custom properties that use
 * light-dark(), so the values live here. The series blue passes contrast (>= 3:1)
 * against both page surfaces (checked with the dataviz palette validator).
 */
export interface ChartTheme {
  series: string;
  /** Same hue, transparent: the min-max range behind the average line. */
  band: string;
  text: string;
  textStrong: string;
  gridline: string;
  axis: string;
  tooltipBackground: string;
}

export const CHART_THEMES: Record<Scheme, ChartTheme> = {
  light: {
    series: '#2a78d6',
    band: 'rgba(42, 120, 214, 0.16)',
    text: '#52514e',
    textStrong: '#0b0b0b',
    gridline: '#e1e0d9',
    axis: '#c3c2b7',
    tooltipBackground: '#fcfcfb',
  },
  dark: {
    series: '#3987e5',
    band: 'rgba(57, 135, 229, 0.22)',
    text: '#c3c2b7',
    textStrong: '#f0efec',
    gridline: '#2c2c2a',
    axis: '#383835',
    tooltipBackground: '#1a1a19',
  },
};
