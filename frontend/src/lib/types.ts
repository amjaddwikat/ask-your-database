import type { Chart, QueryData, ResponseType, StepTrace } from "./api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "error" | "warning";
  content: string;
  responseType?: ResponseType;
  query?: QueryData | null;
  chart?: Chart | null;
  trace?: StepTrace[];
}
