import { Button } from "../ui/Button";
import styles from "../SignInScreen.module.css";

/** A signed-in person the door knows and gave no role: said plainly, with the way to try another account. */
export function NoAccessScreen({ onSignIn }: { onSignIn: () => void }) {
  return (
    <main className={styles.screen}>
      <h1 className={styles.title}>No access</h1>
      <p className={styles.text}>
        This account has no access to the archive. Ask an admin to give it a role, then sign in again.
      </p>
      <Button tone="primary" onClick={onSignIn}>
        Sign in again
      </Button>
    </main>
  );
}
