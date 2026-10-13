## 1. Tylko Gemini

- [x] 1.1 Usunąć `direct`, łańcuch, `listens`, `Deferred`, wybór języka napisów, sufit i odpoczynek napisów, zależność `youtube-transcript-api`
- [x] 1.2 `YOUTUBE_TRANSCRIBER` (`gemini` | `sim`) i `YOUTUBE_TRANSCRIBER_COOLDOWN_MINUTES`; wycofane ustawienia w `scripts/dev.py`
- [x] 1.3 Symulacja z jednym `SimTranscriber`; scenariusz domyślny na `speech`
- [x] 1.4 Testy pętli, symulacji i ustawień przepisane; README, `.env.example`, objaśnienie
- [ ] 1.5 Terraform: `YOUTUBE_TRANSCRIBER=gemini` przed wdrożeniem obrazu; po wdrożeniu usunąć `YOUTUBE_TRANSCRIPT_PROVIDERS`
