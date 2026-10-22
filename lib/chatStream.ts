/**
 * Reader for the terminal's streamed replies (`POST /api/chat/stream`).
 *
 * The agent answers with Server-Sent Events over a normal POST response:
 *   data: {"delta": "some text"}      one per streamed piece
 *   data: {"done": true}              the reply finished
 *   data: {"error": "llm_unavailable"} no model could answer; use the local fallback
 *
 * SSE over fetch rather than a websocket: tokens only flow one way, and a
 * plain POST needs no connection management or reconnect logic.
 */

export type StreamEvent =
  | { delta: string }
  | { done: true }
  | { error: string };

/**
 * Read an SSE response body, calling `onEvent` for every `data:` event.
 * Resolves when the stream ends. Malformed lines are skipped.
 */
export async function readChatStream(
  res: Response,
  onEvent: (ev: StreamEvent) => void
): Promise<void> {
  if (!res.body) throw new Error('no response body');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Events are separated by a blank line.
    let sep = buffer.indexOf('\n\n');
    while (sep !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()) as StreamEvent);
        } catch {
          // ignore a malformed event rather than dropping the whole reply
        }
      }
      sep = buffer.indexOf('\n\n');
    }
  }
}
