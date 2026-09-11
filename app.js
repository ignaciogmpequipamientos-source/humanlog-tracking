const form = document.querySelector("#tracking-form");
const input = document.querySelector("#pedido");
const result = document.querySelector("#result");
const button = form.querySelector("button");

function renderIdle() {
  result.innerHTML = "";
}

function renderLoading() {
  result.innerHTML = `
    <div class="result-card">
      <p class="status">Buscando</p>
      <p class="detail">Consultando el pedido ${escapeHtml(input.value.trim())}.</p>
    </div>
  `;
}

function renderFound(data) {
  result.innerHTML = `
    <div class="result-card">
      <p class="status success">Guia encontrada</p>
      <p class="guide">${escapeHtml(data.guia)}</p>
      <p class="detail">
        Pedido ${escapeHtml(data.pedido)}
        ${data.destinatario ? ` - ${escapeHtml(data.destinatario)}` : ""}
        ${data.provincia ? ` - ${escapeHtml(data.provincia)}` : ""}
      </p>
    </div>
  `;
}

function renderNotFound(pedido) {
  result.innerHTML = `
    <div class="result-card">
      <p class="status error">No encontrado</p>
      <p class="detail">
        No encontramos una guia para el pedido ${escapeHtml(pedido)}.
      </p>
    </div>
  `;
}

function renderError(message) {
  result.innerHTML = `
    <div class="result-card">
      <p class="status error">No se pudo consultar</p>
      <p class="detail">${escapeHtml(message)}</p>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return entities[char];
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const pedido = input.value.trim().replace(/'/g, "");
  if (!pedido) {
    renderIdle();
    input.focus();
    return;
  }

  button.disabled = true;
  renderLoading();

  try {
    const response = await fetch(`/api/search?pedido=${encodeURIComponent(pedido)}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Intentalo nuevamente en unos minutos.");
    }

    if (data.found) {
      renderFound(data);
    } else {
      renderNotFound(pedido);
    }
  } catch (error) {
    renderError(error.message);
  } finally {
    button.disabled = false;
  }
});
