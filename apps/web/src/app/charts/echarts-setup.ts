/**
 * Registers only the ECharts parts the app uses, which keeps the chart bundle small.
 * Loaded lazily (see app.config.ts), so pages without charts never download it.
 */
import { LineChart } from 'echarts/charts';
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer]);

export { echarts };
