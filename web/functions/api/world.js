import { fetchWorld, jsonResponse } from "../_lib/github.js";

export async function onRequestGet() {
  try {
    const contributions = await fetchWorld();
    return jsonResponse({ contributions });
  } catch (err) {
    return jsonResponse({ error: String(err) }, 502);
  }
}

export async function onRequestOptions() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
    },
  });
}
