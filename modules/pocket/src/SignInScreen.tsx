import { Button } from "./ui/Button";
import styles from "./SignInScreen.module.css";

/** What a deployed copy shows before the operator has a session. Not a banner over the list: without a
 *  token every read is a 401, and a screen of empty cards would say the archive is empty. */
export function SignInScreen({ onSignIn }: { onSignIn: () => void }) {
  return (
    <main className={styles.screen}>
      <h1 className={styles.title}>Pocket</h1>
      <p className={styles.text}>
        The prediction-market archive reads as the signed-in operator. Sign in to see what is under
        observation.
      </p>
      <Button tone="primary" onClick={onSignIn}>
        Sign in
      </Button>
    </main>
  );
}
