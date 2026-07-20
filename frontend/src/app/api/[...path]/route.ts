import { NextRequest, NextResponse } from "next/server";

/**
 * API Proxy Route
 *
 * This is the central proxy that forwards ALL API requests from the frontend
 * to the FastAPI backend running on localhost:8000.
 *
 * Path: /api/[...path] → http://localhost:8000/api/v1/[...path]
 *
 * This route handles:
 * - Request forwarding with proper headers
 * - Authentication token passthrough
 * - Error handling and response transformation
 * - All HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS)
 * - CORS headers for cross-origin requests
 */

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

async function proxyRequest(request: NextRequest): Promise<NextResponse> {
  const { method } = request;
  const path = request.nextUrl.pathname.replace(/^\/api/, "/api/v1");
  const searchParams = request.nextUrl.searchParams.toString();
  const targetUrl = `${BACKEND_URL}${path}${searchParams ? `?${searchParams}` : ""}`;

  // Build headers from the original request
  const headers = new Headers();
  headers.set("Content-Type", "application/json");

  // Forward authorization header
  const authHeader = request.headers.get("Authorization");
  if (authHeader) {
    headers.set("Authorization", authHeader);
  }

  // Forward other relevant headers
  const forwardedHeaders = [
    "Accept",
    "Accept-Language",
    "X-Request-ID",
    "X-Forwarded-For",
  ];

  for (const header of forwardedHeaders) {
    const value = request.headers.get(header);
    if (value) {
      headers.set(header, value);
    }
  }

  try {
    // Build fetch options
    const fetchOptions: RequestInit = {
      method,
      headers,
      signal: AbortSignal.timeout(30000), // 30s timeout
    };

    // Include body for non-GET/HEAD requests
    if (method !== "GET" && method !== "HEAD") {
      const body = await request.text();
      if (body) {
        fetchOptions.body = body;
      }
    }

    // Forward the request to the backend
    const backendResponse = await fetch(targetUrl, fetchOptions);

    // Build the response
    const responseHeaders = new Headers();

    // CORS headers
    responseHeaders.set("Access-Control-Allow-Origin", "*");
    responseHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS");
    responseHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID");
    responseHeaders.set("Access-Control-Max-Age", "86400");

    // Forward content type
    const contentType = backendResponse.headers.get("Content-Type");
    if (contentType) {
      responseHeaders.set("Content-Type", contentType);
    }

    // Handle non-JSON responses (like SSE or file downloads)
    const isJson = contentType?.includes("application/json");

    if (isJson || !contentType) {
      const data = await backendResponse.text();

      return new NextResponse(data, {
        status: backendResponse.status,
        statusText: backendResponse.statusText,
        headers: responseHeaders,
      });
    }

    // For non-JSON responses, stream the body
    const responseBody = backendResponse.body;

    return new NextResponse(responseBody, {
      status: backendResponse.status,
      statusText: backendResponse.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("[API Proxy] Error forwarding request:", {
      method,
      path,
      error: error instanceof Error ? error.message : "Unknown error",
    });

    // Return a structured error response
    const isTimeout = error instanceof Error && error.name === "TimeoutError";
    const isConnectionRefused =
      error instanceof Error && error.message.includes("ECONNREFUSED");

    let statusCode = 502;
    let errorCode = "PROXY_ERROR";
    let errorMessage = "Failed to connect to the backend service";

    if (isTimeout) {
      statusCode = 504;
      errorCode = "GATEWAY_TIMEOUT";
      errorMessage = "The backend service did not respond in time";
    } else if (isConnectionRefused) {
      statusCode = 503;
      errorCode = "SERVICE_UNAVAILABLE";
      errorMessage =
        "The backend service is currently unavailable. Please try again later.";
    }

    return NextResponse.json(
      {
        success: false,
        error: {
          code: errorCode,
          message: errorMessage,
        },
      },
      {
        status: statusCode,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  }
}

// ---- HTTP Method Handlers ----

export async function GET(request: NextRequest): Promise<NextResponse> {
  return proxyRequest(request);
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  return proxyRequest(request);
}

export async function PUT(request: NextRequest): Promise<NextResponse> {
  return proxyRequest(request);
}

export async function PATCH(request: NextRequest): Promise<NextResponse> {
  return proxyRequest(request);
}

export async function DELETE(request: NextRequest): Promise<NextResponse> {
  return proxyRequest(request);
}

export async function OPTIONS(): Promise<NextResponse> {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Request-ID",
      "Access-Control-Max-Age": "86400",
    },
  });
}
