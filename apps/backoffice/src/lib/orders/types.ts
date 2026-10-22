// Forme des commandes echangees avec /bff/orders (miroir de l'API d'administration de shop, lecture seule).

export interface OrderSummary {
  id: string;
  number: string;
  status: string;
  email: string;
  total_cents: number;
  item_count: number;
  created_at: string;
}

export interface OrderPage {
  items: OrderSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface OrderLine {
  name: string;
  unit_price_cents: number;
  quantity: number;
  line_total_cents: number;
}

export interface ShippingAddress {
  full_name: string;
  line1: string;
  line2: string | null;
  postal_code: string;
  city: string;
  country: string;
}

export interface OrderDetail {
  id: string;
  number: string;
  status: string;
  email: string;
  shipping_address: ShippingAddress;
  lines: OrderLine[];
  subtotal_cents: number;
  shipping_cents: number;
  total_cents: number;
  created_at: string;
}
