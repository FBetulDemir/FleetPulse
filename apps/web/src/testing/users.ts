import { User } from '../app/api/models';

export function user(overrides: Partial<User> = {}): User {
  return {
    id: '5b0e3c1a-7d8e-4f61-9a2b-1c3d4e5f6a7b',
    email: 'demo-operator@example.com',
    display_name: 'Demo Operator',
    role: 'operator',
    ...overrides,
  };
}
