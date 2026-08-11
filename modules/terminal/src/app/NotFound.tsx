import { Link } from "react-router";
import { DEFAULT_TAB_PATH } from "./tabs";

export function NotFound() {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="text-center">
        <p className="text-lg text-ink">No tab lives at this address.</p>
        <Link to={`/${DEFAULT_TAB_PATH}`} className="mt-3 inline-block text-primary hover:underline">
          Back to {DEFAULT_TAB_PATH}
        </Link>
      </div>
    </div>
  );
}
