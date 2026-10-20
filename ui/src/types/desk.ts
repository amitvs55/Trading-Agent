// The paper trading desk (api/routes/desk.py): your own orders on live prices, with real charges.

export type Side = "BUY" | "SELL";
export type Product = "MIS" | "NRML";
export type OrderType = "MARKET" | "LIMIT" | "SL" | "SL-M";
export type OrderStatus = "AMO" | "PENDING" | "OPEN" | "TRIGGERED" | "FILLED" | "CANCELLED" | "REJECTED";

export interface ChargeParts {
  brokerage: number;
  stt: number;
  exchange: number;
  sebi: number;
  stamp: number;
  gst: number;
  total?: number;
}

export interface DeskQuote {
  bid: number | null;
  ask: number | null;
  ltp: number | null;
  source: string;
}

export interface DeskOrder {
  id: string;
  created_at: string;
  updated_at: string;
  symbol: string;
  token: number;
  index_name: string | null;
  expiry: string | null;
  strike: number | null;
  right: "CE" | "PE" | null;
  lot_size: number;
  side: Side;
  product: Product;
  product_label: string;
  order_type: OrderType;
  qty: number;
  lots: number;
  price: number | null;
  trigger_price: number | null;
  status: OrderStatus;
  status_label: string;
  reason: string | null;
  block: number | null;
  fill_price: number | null;
  filled_at: string | null;
  fill_source: string | null;
  charges: ChargeParts | null;
  source: string | null;
  active: boolean;
}

export interface DeskPosition {
  symbol: string;
  token: number;
  product: Product;
  product_label: string;
  index_name: string | null;
  expiry: string | null;
  strike: number | null;
  right: "CE" | "PE" | null;
  lot_size: number;
  qty: number;
  lots: number;
  avg: number | null;
  invested: number;
  ltp: number | null;
  bid: number | null;
  ask: number | null;
  mark_source: string | null;
  pnl: number | null;
  pnl_pct: number | null;
  buy_charges: number;
  realised: number;
  realised_today: number;
  bought: number;
  sold: number;
  avg_buy: number | null;
  avg_sell: number | null;
  opened_at: string | null;
  open: boolean;
}

export interface DeskTrade {
  id: string;
  symbol: string;
  token: number;
  product: Product;
  qty: number;
  lots: number;
  entry: number;
  exit: number;
  entry_at: string | null;
  exit_at: string;
  reason: string;
  source: string | null;
  gross: number;
  charges: number;
  charges_detail: ChargeParts;
  net: number;
  net_pct: number | null;
}

export interface DeskMarket {
  open: boolean;
  live: boolean;
  next_open: string;
  square_off: string;
}

export interface Desk {
  account: { funds: number; added: number; started_at: string; epoch: number };
  funds: { start: number; cash: number; blocked: number; available: number; invested: number; value: number;
           equity: number; total_pnl: number; return_pct: number | null };
  today: { realised: number; unrealised: number; pnl: number; charges: number };
  stats: { trades: number; wins: number; win_rate: number | null; realised: number; best: number | null;
           worst: number | null; max_drawdown: number; charges_paid: number; charges_detail: ChargeParts };
  positions: DeskPosition[];
  trades: DeskTrade[];
  days: { day: string; trades: number; net: number; charges: number }[];
  curve: { t: string; balance: number; id?: string }[];
  orders: DeskOrder[];
  market: DeskMarket;
  rates: { brokerage_per_order: number; stt_sell_pct: number; exchange_pct: number; sebi_pct: number;
           stamp_buy_pct: number; gst_pct: number };
  tick: number;
  as_of: string;
}

export interface TicketInfo {
  contract: { symbol: string; token: number; index: string; expiry: string; strike: number; right: "CE" | "PE"; lot_size: number };
  quote: DeskQuote | null;
  held: Record<Product, number>;
  selling: Record<Product, number>;
  estimate: { price: number | null; value: number | null; charges: ChargeParts | null; block: number | null; breakeven: number | null };
  available: number;
  problem: string | null;
  market: DeskMarket;
}
