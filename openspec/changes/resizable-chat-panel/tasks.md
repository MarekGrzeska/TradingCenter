## 1. Szerokość w sklepie

- [x] 1.1 `agent/agentChatStore.ts`: `width` w stanie, `setWidth`, odczyt i zapis w
      `localStorage` pod własnym kluczem, odporny na `Storage`, który rzuca (D1)
- [x] 1.2 Granice: dolna stała, górna liczona z szerokości okna; sprowadzanie do granicy
      przy odczycie (D3)
- [x] 1.3 Testy sklepu: szerokość przeżywa ponowne utworzenie sklepu; popsuty wpis daje
      domyślną; wartość spoza granic wraca na granicę

## 2. Chwyt

- [x] 2.1 `agent/AgentChat.tsx`: element o roli `separator` na lewej krawędzi panelu, z
      `aria-label`, `aria-orientation` i wartościami `aria-value*` (D2)
- [x] 2.2 Ciągnięcie myszą przez `pointerdown` + `setPointerCapture`
- [x] 2.3 Klawiatura: strzałki krok po kroku, `Home`/`End` do granic
- [x] 2.4 Szerokość panelu z `style`, nie z klasy Tailwinda (D4)
- [x] 2.5 Sprowadzenie szerokości do granicy przy zmianie rozmiaru okna

## 3. Testy panelu

- [x] 3.1 Ciągnięcie zmienia szerokość i zatrzymuje się na granicach
- [x] 3.2 Chwyt obsłużony z klawiatury zmienia szerokość
- [x] 3.3 Zwinięcie i rozwinięcie wraca do ustawionej szerokości, nie do domyślnej
- [x] 3.4 Okno węższe niż zapamiętana szerokość otwiera panel na granicy

## 4. Domknięcie

- [x] 4.1 `pnpm test`, `pnpm lint`, `pnpm typecheck`
- [ ] 4.2 (operatora) Sprawdzić na żywo z siatką wykresów, czy ciągnięcie nie zacina się przy
      przerysowaniu — i dopiero jeśli tak, wprowadzić `requestAnimationFrame` (Risks)
- [x] 4.3 `openspec validate resizable-chat-panel --strict`
- [x] 4.4 `review.md`, jeżeli będzie co powiedzieć poza tym, co mówią testy
