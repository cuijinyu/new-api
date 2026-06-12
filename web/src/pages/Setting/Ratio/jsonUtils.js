export function parseJsonObject(value, fallback = {}) {
  if (value === undefined || value === null || value === '') return fallback;
  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) : value;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed
      : fallback;
  } catch (error) {
    return fallback;
  }
}

export function parseJsonObjectWithError(value, key) {
  if (!value || !String(value).trim()) return { data: {}, error: null };
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { data: parsed, error: null };
    }
    return { data: {}, error: null };
  } catch (error) {
    return { data: {}, error: `${key}: ${error.message}` };
  }
}
