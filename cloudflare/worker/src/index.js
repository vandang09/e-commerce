const SECURITY_HEADERS = {
  'strict-transport-security': 'max-age=31536000',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'strict-origin-when-cross-origin',
};

export default {
  async fetch(request, env) {
    const publicUrl = new URL(request.url);
    const headers = new Headers(request.headers);
    const clientIp = request.headers.get('cf-connecting-ip');

    headers.delete('x-forwarded-for');
    headers.set('x-forwarded-host', publicUrl.host);
    headers.set('x-forwarded-proto', publicUrl.protocol.slice(0, -1));
    if (clientIp) headers.set('x-forwarded-for', clientIp);

    let upstreamResponse;
    try {
      upstreamResponse = await env.FLASK_ORIGIN.fetch(new Request(request, { headers }));
    } catch (error) {
      console.error('Private Flask origin request failed:', error);
      return new Response('Application origin unavailable.', {
        status: 502,
        headers: { 'content-type': 'text/plain; charset=utf-8' },
      });
    }

    const responseHeaders = new Headers(upstreamResponse.headers);
    for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
      responseHeaders.set(name, value);
    }
    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: responseHeaders,
    });
  },
};
