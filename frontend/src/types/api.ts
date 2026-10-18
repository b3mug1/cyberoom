export type Computer = {
  id: string;
  name: string;
  cpu: string;
  gpu: string;
  ram_gb: number;
  storage: string;
  monitor: string;
  refresh_rate: number;
  status: "AVAILABLE" | "OCCUPIED" | "MAINTENANCE" | "DISABLED";
  is_active: boolean;
};

export type Tariff = {
  id: string;
  name: string;
  price_per_hour: string;
  start_time: string;
  end_time: string;
};

export type ClubPriceMenu = {
  currency: string;
  holiday_note: string;
  tiers: Array<{
    name: string;
    weekdays: {
      day_hours: string;
      day_price: number;
      hourly: number;
      deals: Array<{ label: string; price: number }>;
      night_hours: string;
      night_price: number;
      turbo_hours: string;
      turbo_price: number;
    };
    weekends: {
      day_hours: string;
      day_price: number;
      hourly: number;
      deals: Array<{ label: string; price: number }>;
      night_hours: string;
      night_price: number;
      turbo_hours: string;
      turbo_price: number;
    };
  }>;
};

export type Club = {
  id: string;
  name: string;
  description: string;
  address: string;
  city: string;
  timezone: string;
  price_menu: ClubPriceMenu;
  phone: string;
  rating: string;
  is_active: boolean;
  computers: Computer[];
  tariffs: Tariff[];
};

export type ClubPage = { items: Club[]; page: number; page_size: number; total: number };

export type Booking = {
  id: string;
  computer_id: string;
  start_time: string;
  end_time: string;
  status: "PENDING" | "CONFIRMED" | "ACTIVE" | "COMPLETED" | "CANCELLED" | "EXPIRED";
  source: "ONLINE" | "WALK_IN";
  total_price: string;
  qr_token: string;
};
