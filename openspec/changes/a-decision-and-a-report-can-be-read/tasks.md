# Tasks — a-decision-and-a-report-can-be-read

## 0. Warunek wejścia

- [ ] 0.1 Na produkcji jest co najmniej jedna decyzja o wejściu i jeden zachowany raport backtestu

## 1. Ekran

- [ ] 1.1 Szczegóły decyzji: odczyty, na których stanęła, i wersja parametrów — obok poziomów i R, które są już w wierszu
- [ ] 1.2 Widok raportów backtestu: metryki z modelem kosztów, wersją parametrów i zakresem danych; bez akcji uruchamiającej
- [ ] 1.3 Testy widoków wedle reguły: ścieżka szczęśliwa, jeden błąd, jedna odmowa

## 2. Sprawdzenie

- [ ] 2.1 `pnpm test`, `lint`, `typecheck`, `contract:check`
- [ ] 2.2 `openspec validate a-decision-and-a-report-can-be-read --strict`
