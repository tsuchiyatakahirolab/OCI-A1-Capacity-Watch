import { CapacityWatchClock } from "./clock";

export { CapacityWatchClock };

export default {
  fetch(): Response {
    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler;
