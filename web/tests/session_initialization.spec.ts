import { expect, it, vi } from "vitest";

it("shares a failed session attempt and allows a fresh retry", async () => {
  vi.resetModules();
  const { ensureProfileSession } = await import("../src/api/profile");
  const failure = new Error("offline");
  const fetchImpl = vi.fn().mockRejectedValueOnce(failure)
    .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "r".repeat(64) })));

  const attempts = await Promise.allSettled([
    ensureProfileSession({ fetchImpl }),
    ensureProfileSession({ fetchImpl }),
  ]);
  expect(attempts.map((result) => result.status)).toEqual(["rejected", "rejected"]);
  expect(fetchImpl).toHaveBeenCalledTimes(1);
  await expect(ensureProfileSession({ fetchImpl })).resolves.toBe("r".repeat(64));
  expect(fetchImpl).toHaveBeenCalledTimes(2);
});
