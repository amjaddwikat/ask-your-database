import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, sendChat } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("sendChat", () => {
  it("posts the message with the API key header", async () => {
    const fetchMock = stubFetch(200, { session_id: "abc12345", type: "general", message: "hi", trace: [] });

    const res = await sendChat("hello", "abc12345");

    expect(res.message).toBe("hi");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/chat$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ message: "hello", session_id: "abc12345" });
    expect(init.headers).toHaveProperty("X-API-Key");
  });

  it("surfaces the error envelope as an ApiError", async () => {
    stubFetch(401, { error: { code: "unauthorized", message: "Invalid API key", request_id: "r1" } });

    const err = await sendChat("hello").catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 401, code: "unauthorized", message: "Invalid API key", requestId: "r1" });
  });

  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(sendChat("hello")).rejects.toMatchObject({ code: "network_error" });
  });
});
