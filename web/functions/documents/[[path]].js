export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const pathParts = url.pathname.split("/").filter(Boolean);
  const docId = pathParts.length >= 2 ? pathParts[1] : "";

  const assetUrl = new URL(context.request.url);
  // Cloudflare Pages canonicalizes URLs by removing .html extensions (308 → /document-view).
  // Use the extension-free path so ASSETS.fetch resolves without redirect.
  assetUrl.pathname = "/document-view";
  assetUrl.search = "";
  if (docId) {
    assetUrl.searchParams.set("docId", docId);
  }

  return context.env.ASSETS.fetch(new Request(assetUrl.toString(), context.request));
}
