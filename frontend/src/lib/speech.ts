/**
 * A thin, typed wrapper over the browser's Web Speech API. Chrome and Edge
 * ship a native recognizer (`webkitSpeechRecognition`); nothing is sent to
 * Tarazu's backend and no API key is involved. Where the API is missing
 * (Firefox, some WebViews) `isSpeechSupported()` is false and the mic button
 * simply does not render.
 *
 * The DOM lib has no types for this API, so the minimal shapes are declared
 * here rather than sprinkling casts through the UI.
 */

interface RecognitionAlternativeLike {
  transcript: string;
}

interface RecognitionResultLike {
  isFinal: boolean;
  0: RecognitionAlternativeLike;
}

interface RecognitionEventLike {
  resultIndex: number;
  results: { length: number; [index: number]: RecognitionResultLike };
}

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
}

type RecognitionCtor = new () => RecognitionLike;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const holder = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return holder.SpeechRecognition ?? holder.webkitSpeechRecognition ?? null;
}

export function isSpeechSupported(): boolean {
  return recognitionCtor() !== null;
}

export interface Recognizer {
  stop(): void;
}

/**
 * Start listening. `onTranscript` fires on every update with the finalised
 * text so far plus the current interim guess — the caller just renders the
 * two concatenated. `onEnd` always fires exactly once, however recognition
 * stops (user, silence timeout, or error).
 */
export function startRecognition(options: {
  lang: string;
  onTranscript: (finalText: string, interimText: string) => void;
  onEnd: () => void;
  onError: (error: string) => void;
}): Recognizer | null {
  const Ctor = recognitionCtor();
  if (!Ctor) return null;

  const recognition = new Ctor();
  recognition.lang = options.lang;
  recognition.continuous = true;
  recognition.interimResults = true;

  let finalText = "";
  let ended = false;

  recognition.onresult = (event) => {
    let interim = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcript = result[0]?.transcript ?? "";
      if (result.isFinal) finalText += transcript;
      else interim += transcript;
    }
    options.onTranscript(finalText, interim);
  };
  recognition.onerror = (event) => {
    // "no-speech" and "aborted" are normal ends, not failures worth surfacing.
    if (event.error !== "no-speech" && event.error !== "aborted") {
      options.onError(event.error);
    }
  };
  recognition.onend = () => {
    if (!ended) {
      ended = true;
      options.onEnd();
    }
  };

  recognition.start();
  return {
    stop() {
      recognition.stop();
    },
  };
}
