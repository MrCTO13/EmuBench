import { sqliteTable, text, integer, index } from "drizzle-orm/sqlite-core";

export const runs = sqliteTable("runs", {
  id: text("id").primaryKey(),
  received: integer("received").notNull(),
  game: text("game").notNull(),
  profile: text("profile").notNull(),
  emulator: text("emulator").notNull(),
  campaign: text("campaign"),
  device: text("device").notNull(),
  payload: text("payload").notNull()
}, table => [
  index("runs_received").on(table.received, table.id),
  index("runs_campaign").on(table.campaign, table.received),
  index("runs_profile").on(table.profile, table.emulator),
  index("runs_device").on(table.device)
]);
