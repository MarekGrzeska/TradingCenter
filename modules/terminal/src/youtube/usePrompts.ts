import { useRead, type Read } from "../data/query";
import type { PromptsPage, YoutubeApi } from "./youtubeApi";

const NONE: PromptsPage = { prompts: [], maxChars: 0, ceiling: 0 };

/** The prompts on offer, read once and kept by every screen that picks one: a dialog opening is not a reason to ask again. */
export function usePrompts(client: YoutubeApi): Read<PromptsPage> {
  return useRead<PromptsPage>({
    key: ["youtube", "prompts"],
    read: (signal) => client.prompts(signal),
    initial: NONE,
    fallbackMessage: "nie udało się wczytać promptów",
  });
}
