CREATE TABLE `installs` (
	`key` text PRIMARY KEY NOT NULL,
	`token_hash` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `limits` (
	`scope` text PRIMARY KEY NOT NULL,
	`window` integer NOT NULL,
	`used` integer NOT NULL
);
