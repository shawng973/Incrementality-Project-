import { redirect } from "next/navigation";

/**
 * Root route — middleware handles the auth redirect, but as a fallback
 * we send logged-in users straight to the tests list.
 */
export default function RootPage() {
  redirect("/tests");
}
