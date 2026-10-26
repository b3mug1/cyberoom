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
  days_of_week: number[];
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
  refund_cutoff_hours: number;
  price_menu: ClubPriceMenu;
  phone: string;
  rating: string;
  is_active: boolean;
  computers: Computer[];
  tariffs: Tariff[];
};

export type Review = {
  id: string;
  club_rating: number;
  computer_rating: number;
  comment: string;
  created_at: string;
};

export type ClubReview = Review & { computer_name: string };

export type WaitlistRequest = {
  id: string;
  club_id: string;
  computer_id: string | null;
  start_time: string;
  end_time: string;
  status: "WAITING" | "NOTIFIED" | "CANCELLED";
  created_at: string;
};

export type UserNotification = {
  id: string;
  booking_id: string | null;
  kind: string;
  title: string;
  message: string;
  payload: Record<string, string>;
  scheduled_at: string;
  read_at: string | null;
};

export type ClubPage = { items: Club[]; page: number; page_size: number; total: number };

export type Booking = {
  id: string;
  computer_id: string;
  club_id: string;
  computer_name: string;
  start_time: string;
  end_time: string;
  status: "PENDING" | "CONFIRMED" | "ACTIVE" | "COMPLETED" | "CANCELLED" | "EXPIRED";
  source: "ONLINE" | "WALK_IN";
  total_price: string;
  refund_cutoff_hours: number;
  subtotal_price: string;
  discount_amount: string;
  promo_code: string | null;
  membership_minutes: number;
  membership_credit_amount: string;
  payment_status: string | null;
  qr_token: string;
  review: Review | null;
};

export type MembershipPlan = {
  id: string;
  club_id: string;
  name: string;
  description: string;
  hours: number;
  price: string;
  validity_days: number;
  is_active: boolean;
};

export type Membership = {
  id: string;
  club_id: string;
  club_name: string;
  plan_name: string;
  total_minutes: number;
  remaining_minutes: number;
  starts_at: string;
  expires_at: string;
};

export type Payment = {
  id: string;
  booking_id: string | null;
  membership_plan_id: string | null;
  amount: string;
  currency: string;
  status: string;
  checkout_url: string | null;
  refund_amount: string;
  created_at: string;
};
