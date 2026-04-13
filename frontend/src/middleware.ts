import { type NextRequest, NextResponse } from "next/server";

export function middleware(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - api routes (FastAPI proxy — not Next.js API routes)
     */
    "/((?!_next/static|_next/image|favicon\\.ico).*)",
  ],
};
