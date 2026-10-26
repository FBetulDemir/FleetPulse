/**
 * Friendly names for the API types generated in `schema.d.ts`.
 * Regenerate with `npm run api:generate` after the backend's API changes.
 */
import { components } from './schema';

type Schemas = components['schemas'];

export type Vessel = Schemas['VesselOut'];
export type VesselPage = Schemas['VesselPage'];
export type VesselType = Schemas['VesselType'];
export type Problem = Schemas['Problem'];
