CREATE TABLE `runs` (
	`id` text PRIMARY KEY NOT NULL,
	`received` integer NOT NULL,
	`game` text NOT NULL,
	`profile` text NOT NULL,
	`emulator` text NOT NULL,
	`campaign` text,
	`device` text NOT NULL,
	`payload` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `runs_received` ON `runs` (`received`,`id`);--> statement-breakpoint
CREATE INDEX `runs_campaign` ON `runs` (`campaign`,`received`);--> statement-breakpoint
CREATE INDEX `runs_profile` ON `runs` (`profile`,`emulator`);--> statement-breakpoint
CREATE INDEX `runs_device` ON `runs` (`device`);