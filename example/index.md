---
layout: page
title: Example
permalink: /example/
---

This page shows an example network and its source YAML. You can also <a href="{{ '/example/example.html' | relative_url }}" target="_blank" rel="noopener noreferrer">view the network in full screen</a>.

<div style="display: grid; grid-template-columns: 1fr; gap: 1rem;">
  <section>
    <h2>Output Network</h2>
    <iframe
      id="network-iframe"
      src="{{ '/example/example.html' | relative_url }}"
      title="Network output"
      style="width: 100%; min-height: 520px; border: 1px solid #ccc; border-radius: 6px;"
      loading="lazy"
      onload="resizeIframe(this)"
    ></iframe>
  </section>

  <section>
    <h2>Input YAML</h2>
{% highlight yaml %}
{% include_relative example.yaml %}
{% endhighlight %}
  </section>
</div>

<script>
function resizeIframe(iframe) {
  try {
    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;

    // Hide h1 in iframe
    const h1 = iframeDoc.querySelector('h1');
    if (h1) h1.style.display = 'none';

    // Derive aspect ratio from the embedded network container.
    const contentTarget = iframeDoc.querySelector('#mynetwork') || iframeDoc.body;
    const targetWidth = contentTarget.clientWidth || 1;
    const targetHeight = contentTarget.clientHeight || iframeDoc.documentElement.scrollHeight || 1;
    const ratio = targetHeight / targetWidth;

    iframe.dataset.aspectRatio = String(ratio > 0 ? ratio : 0.62);
    applyIframeHeight(iframe);

    // Keep height synced with iframe width changes.
    if (!iframe.dataset.resizeBound) {
      window.addEventListener('resize', function () {
        applyIframeHeight(iframe);
      });
      iframe.dataset.resizeBound = 'true';
    }
  } catch(e) {
    console.warn('Cannot resize iframe from content:', e);
    iframe.style.height = '70vh';
  }
}

function applyIframeHeight(iframe) {
  const ratio = Number(iframe.dataset.aspectRatio || 0.62);
  const computedHeight = Math.round(iframe.clientWidth * ratio);
  const minHeight = 520;
  iframe.style.height = Math.max(computedHeight, minHeight) + 'px';
}
</script>
