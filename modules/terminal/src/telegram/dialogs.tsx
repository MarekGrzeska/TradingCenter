import { useEffect, useRef, useState } from "react";
import { safeLocalStorage } from "../data/storage";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { botUsernameProblem, keyProblem } from "./present";
import { QrCode } from "./QrCode";
import type { Bot, CodeDelivery, Destination, StartLink, TelegramApi } from "./telegramApi";

/**
 * The questions this tab asks. A refusal from the door — a wrong code, an assignment still pointing at what is being removed,
 * a setting it names — stays in the dialog with the door's own words: it answers what was asked, it is not a failure of the screen.
 */

const INPUT = "rounded border border-border bg-sunken px-2 py-1 text-ink";
const signal = () => new AbortController().signal;

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-ink-secondary">{label}</span>
      {children}
      {hint && <span className="text-ink-faint">{hint}</span>}
    </label>
  );
}

type Step = "phone" | "code" | "password";

// The owner account's number, kept in this browser after the first code was sent, so the next login is one click. In the
// browser and not in the code: the terminal's bundle is downloadable without signing in, and git keeps what it is given.
const PHONE_KEY = "tc.telegram.ownerPhone";

function rememberedPhone(): string {
  try {
    return safeLocalStorage()?.getItem(PHONE_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberPhone(phone: string): void {
  try {
    safeLocalStorage()?.setItem(PHONE_KEY, phone);
  } catch {
    // A browser that will not keep it asks again next time; nothing else depends on it.
  }
}

/** Said, because "a code was sent" is no help to somebody looking in the wrong place. */
const DELIVERY_TEXT: Record<CodeDelivery, string> = {
  app: "Kod poszedł do aplikacji Telegram zalogowanej na tym koncie — szukaj wiadomości od „Telegram” (czat serwisowy).",
  sms: "Kod poszedł SMS-em na ten numer.",
  call: "Telegram zadzwoni na ten numer i poda kod.",
  other: "Telegram wysłał kod inną drogą niż aplikacja czy SMS.",
};

/** Telegram's steps in Telegram's order. The number is the only thing remembered between them, and only to say which. */
export function LoginDialog({
  api,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  onClose(): void;
  onDone(): void;
}) {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState(rememberedPhone);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [delivery, setDelivery] = useState<CodeDelivery | null>(null);
  const [resending, setResending] = useState(false);
  const [resendFailure, setResendFailure] = useState<string | null>(null);

  const labels: Record<Step, { title: string; confirm: string; busy: string; disabled: boolean }> = {
    phone: { title: "Zaloguj konto-właściciela", confirm: "Wyślij kod", busy: "Pytam Telegram…", disabled: phone.trim() === "" },
    code: { title: "Kod z Telegrama", confirm: "Zaloguj", busy: "Loguję…", disabled: code.trim() === "" },
    password: { title: "Hasło dwuetapowe", confirm: "Zaloguj", busy: "Loguję…", disabled: password === "" },
  };
  const now = labels[step];

  async function advance(): Promise<void> {
    const result =
      step === "phone"
        ? await api.loginStart(phone.trim(), signal())
        : step === "code"
          ? await api.loginCode(code.trim(), signal())
          : await api.loginPassword(password, signal());
    // After Telegram accepted it, and not before: a typo must not become the number offered next time.
    if (step === "phone") rememberPhone(phone.trim());
    if (result.step === "done") {
      onDone();
      onClose();
      return;
    }
    if (result.step === "code") setDelivery(result.delivery);
    setStep(result.step);
  }

  async function resend(): Promise<void> {
    setResendFailure(null);
    setResending(true);
    try {
      const result = await api.loginResend(signal());
      if (result.step === "code") setDelivery(result.delivery);
    } catch (cause: unknown) {
      setResendFailure(cause instanceof Error ? cause.message : "nie udało się poprosić o kod jeszcze raz");
    } finally {
      setResending(false);
    }
  }

  return (
    <ConfirmDialog
      title={now.title}
      confirmLabel={now.confirm}
      busyLabel={now.busy}
      confirmDisabled={now.disabled}
      fallbackError="logowanie się nie udało"
      closeOnSuccess={false}
      onConfirm={advance}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        {step === "phone" && (
          <>
            <p className="rounded bg-warning-soft px-2 py-1 text-xs text-warning">
              Użyj <strong>osobnego konta tylko do botów</strong> (z hasłem dwuetapowym), nie swojego prywatnego. Sesja tego
              konta pozwala pisać jako boty, którym ufasz.
            </p>
            <Field label="Numer telefonu konta" hint="W formie międzynarodowej, np. +48123456789. Telegram wyśle kod do aplikacji.">
              <input
                className={INPUT}
                value={phone}
                autoFocus
                inputMode="tel"
                autoComplete="off"
                placeholder="+48123456789"
                onChange={(e) => setPhone(e.target.value)}
              />
            </Field>
          </>
        )}
        {step === "code" && (
          <>
            {delivery !== null && <p className="text-xs text-ink-secondary">{DELIVERY_TEXT[delivery]}</p>}
            <Field label="Kod, który przyszedł do Telegrama" hint="Zły kod nie kończy logowania — można podać kolejny.">
              <input
                className={INPUT}
                value={code}
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                onChange={(e) => setCode(e.target.value)}
              />
            </Field>
            <div className="flex flex-col gap-1">
              <button
                type="button"
                className="self-start text-xs text-primary underline disabled:opacity-40"
                disabled={resending}
                onClick={() => void resend()}
              >
                {resending ? "Proszę o kod…" : "Nie dostałem kodu — wyślij inaczej"}
              </button>
              {resendFailure !== null && <p className="text-xs text-critical">{resendFailure}</p>}
              <p className="text-xs text-ink-faint">
                Telegram próbuje po kolei: aplikacja, SMS, telefon. Poczekaj chwilę między próbami — zbyt wiele próśb o kod
                zostaje ograniczone.
              </p>
            </div>
          </>
        )}
        {step === "password" && (
          <Field label="Hasło dwuetapowe tego konta">
            <input
              className={INPUT}
              type="password"
              value={password}
              autoFocus
              autoComplete="off"
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        )}
      </div>
    </ConfirmDialog>
  );
}

export function LogoutDialog({
  api,
  username,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  username: string | null;
  onClose(): void;
  onDone(): void;
}) {
  const [endedAtTelegram, setEnded] = useState<boolean | null>(null);

  if (endedAtTelegram !== null) {
    return (
      <ConfirmDialog
        title="Konto wylogowane"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          {endedAtTelegram
            ? "Sesja została zakończona w Telegramie i usunięta stąd."
            : "Sesja została usunięta stąd, ale Telegram nie odpowiedział — zakończ to urządzenie w ustawieniach Telegrama (Urządzenia)."}
        </p>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Wyloguj konto"
      confirmLabel="Wyloguj"
      busyLabel="Wylogowuję…"
      tone="danger"
      fallbackError="nie udało się wylogować"
      closeOnSuccess={false}
      onConfirm={async () => {
        setEnded(await api.logout(signal()));
        onDone();
      }}
      onClose={onClose}
    >
      <p className="text-xs text-ink-secondary">
        <span className="text-ink">{username ?? "Konto"}</span> przestaje być zalogowane. Boty i odbiorcy zostają i dalej
        dostają wiadomości — znika tylko możliwość zakładania, usuwania i rotacji botów, dopóki konta nie zalogujesz ponownie.
      </p>
    </ConfirmDialog>
  );
}

export function CreateBotDialog({
  api,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  onClose(): void;
  onDone(bot: Bot): void;
}) {
  const [title, setTitle] = useState("");
  const [username, setUsername] = useState("");
  const problem = botUsernameProblem(username);

  return (
    <ConfirmDialog
      title="Utwórz bota"
      confirmLabel="Utwórz"
      busyLabel="Rozmawiam z BotFatherem…"
      confirmDisabled={title.trim() === "" || username.trim() === "" || problem !== null}
      fallbackError="nie udało się utworzyć bota"
      onConfirm={async () => {
        onDone(await api.createBot(title.trim(), username.trim().replace(/^@/, ""), signal()));
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <Field label="Nazwa wyświetlana">
          <input className={INPUT} value={title} autoFocus placeholder="TradingCenter alerty" onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Nazwa użytkownika bota" hint={problem ?? "Musi kończyć się na „bot”. Telegram dopuszcza do 20 botów na konto."}>
          <input className={INPUT} value={username} placeholder="tc_alerty_bot" onChange={(e) => setUsername(e.target.value)} />
        </Field>
      </div>
    </ConfirmDialog>
  );
}

export function AdoptBotDialog({
  api,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  onClose(): void;
  onDone(bot: Bot): void;
}) {
  const [token, setToken] = useState("");

  return (
    <ConfirmDialog
      title="Dodaj istniejącego bota"
      confirmLabel="Dodaj"
      busyLabel="Pytam Telegram, czyj to token…"
      confirmDisabled={token.trim() === ""}
      fallbackError="nie udało się dodać bota"
      onConfirm={async () => {
        onDone(await api.adoptBot(token.trim(), signal()));
      }}
      onClose={onClose}
    >
      <Field
        label="Token od @BotFathera"
        hint="Zapisuje się w bazie i nigdy nie wraca w żadnej odpowiedzi. Bota dodanego tokenem nie da się usunąć stąd w BotFatherze — tylko zapomnieć."
      >
        <input
          className={INPUT}
          type="password"
          value={token}
          autoFocus
          autoComplete="off"
          onChange={(e) => setToken(e.target.value)}
        />
      </Field>
    </ConfirmDialog>
  );
}

const POLL_MS = 3000;

/**
 * The one tap a bot cannot do for itself. Asks for a name, shows the link and its code, and watches for the tap: the
 * destination turns "odbiera" without a reload. The watching runs only while this is open and the tab is visible.
 */
export function ActivateDialog({
  api,
  bot,
  existing,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  bot: Bot;
  /** When set, a fresh link for a destination that already has a name — an expired one, or a blocked one. */
  existing?: Destination;
  onClose(): void;
  onDone(): void;
}) {
  const [name, setName] = useState(existing?.name ?? "operator");
  const [link, setLink] = useState<StartLink | null>(null);
  const [received, setReceived] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [renewing, setRenewing] = useState(false);
  const [renewFailure, setRenewFailure] = useState<string | null>(null);
  // The watching must not restart each time the parent renders a fresh callback, or the interval never gets to fire.
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (link === null || received) return;
    const timer = setInterval(() => {
      setNow(Date.now());
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      void api
        .destinations(signal())
        .then((all) => {
          if (all.some((one) => one.name === link.destination.name && one.receives)) {
            setReceived(true);
            done.current();
          }
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, link, received]);

  if (received) {
    return (
      <ConfirmDialog
        title="Odbiorca aktywny"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          <span className="text-ink">{link?.destination.name}</span> odbiera wiadomości od @{bot.username}. Przypisz mu teraz
          cele w sekcji poniżej.
        </p>
      </ConfirmDialog>
    );
  }

  if (link !== null && now >= link.expiresAt.getTime()) {
    return (
      <ConfirmDialog
        title="Odnośnik wygasł"
        confirmLabel={renewing ? "Wydaję…" : "Wydaj nowy link"}
        busyLabel="Wydaję…"
        confirmDisabled={renewing}
        fallbackError="nie udało się wydać nowego linku"
        closeOnSuccess={false}
        onConfirm={async () => {
          setRenewFailure(null);
          setRenewing(true);
          try {
            const fresh = await api.offerDestination(link.destination.name, bot.username, signal());
            setLink(fresh);
            setNow(Date.now());
          } catch (cause: unknown) {
            setRenewFailure(cause instanceof Error ? cause.message : "nie udało się wydać nowego linku");
          } finally {
            setRenewing(false);
          }
        }}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          Nikt nie dotknął „Start” w ciągu 30 minut, więc ten link już nic nie wiąże. Odbiorca{" "}
          <span className="text-ink">{link.destination.name}</span> dalej istnieje — wystarczy wydać nowy link.
        </p>
        {renewFailure !== null && <p className="mt-2 text-xs text-critical">{renewFailure}</p>}
      </ConfirmDialog>
    );
  }

  if (link !== null) {
    return (
      <ConfirmDialog
        title="Dotknij „Start” w Telegramie"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <div className="flex flex-col items-center gap-3 text-xs text-ink-secondary">
          <p>
            Z konta, które ma dostawać alerty, zeskanuj kod albo otwórz link i naciśnij <strong>Start</strong>. Ważne do{" "}
            {link.expiresAt.toLocaleTimeString("pl-PL")}; to okno samo zauważy tapnięcie.
          </p>
          <QrCode text={link.url} label={`Kod QR odnośnika startowego @${bot.username}`} />
          <a className="break-all text-primary underline" href={link.url} target="_blank" rel="noreferrer">
            {link.url}
          </a>
        </div>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title={`Aktywuj odbiorcę przez @${bot.username}`}
      confirmLabel="Pokaż link"
      busyLabel="Przygotowuję…"
      confirmDisabled={name.trim() === ""}
      fallbackError="nie udało się przygotować odbiorcy"
      closeOnSuccess={false}
      onConfirm={async () => {
        setLink(await api.offerDestination(name.trim(), bot.username, signal()));
      }}
      onClose={onClose}
    >
      <Field
        label="Nazwa odbiorcy"
        hint="To nazwa w przypisaniach, nie czat — przeżywa wymianę bota. Bot nie może odezwać się pierwszy, więc ktoś musi raz dotknąć linku."
      >
        <input className={INPUT} value={name} autoFocus disabled={existing !== undefined} onChange={(e) => setName(e.target.value)} />
      </Field>
    </ConfirmDialog>
  );
}

export function ConfirmRemoval({
  title,
  confirmLabel,
  body,
  fallbackError,
  onConfirm,
  onClose,
}: {
  title: string;
  confirmLabel: string;
  body: React.ReactNode;
  fallbackError: string;
  onConfirm(): Promise<void>;
  onClose(): void;
}) {
  return (
    <ConfirmDialog
      title={title}
      confirmLabel={confirmLabel}
      busyLabel="Pracuję…"
      tone="danger"
      fallbackError={fallbackError}
      onConfirm={onConfirm}
      onClose={onClose}
    >
      <div className="flex flex-col gap-2 text-xs text-ink-secondary">{body}</div>
    </ConfirmDialog>
  );
}

export function AssignDialog({
  api,
  destinations,
  initialKey = "",
  onClose,
  onDone,
}: {
  api: TelegramApi;
  destinations: Destination[];
  initialKey?: string;
  onClose(): void;
  onDone(): void;
}) {
  const [key, setKey] = useState(initialKey);
  const [destination, setDestination] = useState(destinations[0]?.name ?? "");
  const problem = keyProblem(key.trim());

  return (
    <ConfirmDialog
      title="Dodaj przypisanie"
      confirmLabel="Przypisz"
      busyLabel="Przypisuję…"
      confirmDisabled={key.trim() === "" || destination === "" || problem !== null}
      fallbackError="nie udało się przypisać"
      onConfirm={async () => {
        await api.assign(key.trim(), destination, signal());
        onDone();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <Field
          label="Cel, przedrostek albo *"
          hint={problem ?? "Przedrostek obejmuje całe segmenty: „youtube” łapie youtube.film.cokolwiek, ale nie youtubers. * to wszystko, czego nic nie złapało."}
        >
          <input className={INPUT} value={key} autoFocus placeholder="youtube.film" onChange={(e) => setKey(e.target.value)} />
        </Field>
        <Field label="Kto ma o tym słyszeć">
          <select className={INPUT} value={destination} onChange={(e) => setDestination(e.target.value)}>
            {destinations.map((one) => (
              <option key={one.name} value={one.name}>
                {one.name} (@{one.bot}) — {one.receives ? "odbiera" : "jeszcze nie odbiera"}
              </option>
            ))}
          </select>
        </Field>
      </div>
    </ConfirmDialog>
  );
}
