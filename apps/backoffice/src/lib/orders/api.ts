import { request } from '../catalog/api';
import type { OrderDetail, OrderPage } from './types';

// Appels du navigateur aux routes serveur du back-office (/bff/orders) : lecture seule, aucun jeton manipule.

export interface OrderListParams {
  q: string;
  status: string;
  offset: number;
  limit: number;
}

export const ordersApi = {
  list({ q, status, offset, limit }: OrderListParams) {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status !== '') query.set('status', status);
    if (q.trim() !== '') query.set('q', q.trim());
    return request<OrderPage>(`/bff/orders?${query}`);
  },
  get(id: string) {
    return request<OrderDetail>(`/bff/orders/${encodeURIComponent(id)}`);
  },
};
