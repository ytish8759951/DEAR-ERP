const AI_FAKE_DATA = {
  product_name: "韓系寬鬆顯瘦短袖上衣",
  size_chart: ["尺寸：F", "肩寬：50", "胸圍：55", "袖長：22", "衣長：62"].join("\n"),
  ai_description: "韓系寬鬆版型設計，修飾身形不挑身材，柔軟舒適布料，日常穿搭輕鬆有型。",
  live_script: "這件版型真的超修飾，穿起來不貼身，單穿好看，搭牛仔褲或短裙都很適合。",
};

function updateVariantRows() {
  const tableBody = document.getElementById("variantRows");
  if (!tableBody) return;

  const colors = [...document.querySelectorAll(".variant-color:checked")].map((item) => ({
    id: item.value,
    name: item.dataset.name,
  }));
  const sizes = [...document.querySelectorAll(".variant-size:checked")].map((item) => ({
    id: item.value,
    name: item.dataset.name,
  }));

  if (!colors.length || !sizes.length) {
    tableBody.innerHTML = '<tr><td colspan="2" class="text-secondary">請勾選顏色與尺寸</td></tr>';
    return;
  }

  const existing = window.existingVariantStocks || {};
  tableBody.innerHTML = "";

  colors.forEach((color) => {
    sizes.forEach((size) => {
      const key = `${color.id}_${size.id}`;
      const stock = existing[key] ?? 0;
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${color.name}${size.name}</td>
        <td>
          <input class="form-control form-control-sm" type="number" min="0" step="1" name="stock_${color.id}_${size.id}" value="${stock}">
        </td>
      `;
      tableBody.appendChild(row);
    });
  });
}

function selectedNames(selector) {
  return [...document.querySelectorAll(`${selector}:checked`)].map((item) => item.dataset.name);
}

function buildLineGroupText() {
  const productName = document.getElementById("productNameInput")?.value.trim() || AI_FAKE_DATA.product_name;
  const price = document.getElementById("productPriceInput")?.value || "590";
  const sizeChart = document.getElementById("sizeChartInput")?.value.trim() || AI_FAKE_DATA.size_chart;
  const colors = selectedNames(".variant-color");
  const sizes = selectedNames(".variant-size");

  return [
    `【${productName}】`,
    "",
    "顏色：",
    colors.length ? colors.join("、") : "白色、黑色、灰色",
    "",
    "尺寸：",
    sizes.length ? sizes.join("、") : "F",
    "",
    "售價：",
    `$${price || "590"}`,
    "",
    "尺寸表：",
    sizeChart,
    "",
    "商品特色：",
    "韓系寬鬆版型",
    "修飾身形不挑人",
    "日常百搭好穿",
    "單穿或內搭都適合",
  ].join("\n");
}

function setAiStatus(message, type = "success") {
  const status = document.getElementById("aiStatus");
  if (!status) return;
  status.className = type === "success" ? "text-success small fw-semibold" : "text-danger small fw-semibold";
  status.textContent = message;
  window.clearTimeout(status.dataset.clearTimer);
  if (type === "success") {
    status.dataset.clearTimer = window.setTimeout(() => {
      status.textContent = "";
      status.className = "small";
    }, 3000);
  }
}

let lastAiRecognition = null;

function normalizeAiText(value) {
  return (value || "").toString().trim().toLowerCase();
}

function aiTextTerms(values) {
  return values
    .flatMap((value) => normalizeAiText(value).split(/[、,，/／\s]+/))
    .map((value) => value.trim())
    .filter(Boolean);
}

function autoCheckOptions(selector, values) {
  const terms = aiTextTerms(values);
  if (!terms.length) return false;
  let changed = false;
  document.querySelectorAll(selector).forEach((option) => {
    const name = normalizeAiText(option.dataset.name);
    if (!name) return;
    const matched = terms.some((term) => term.includes(name) || name.includes(term));
    if (matched && !option.checked) {
      option.checked = true;
      changed = true;
    }
  });
  return changed;
}

function recognitionSummary(data) {
  if (!data) return "";
  return [
    `商品名稱：${data.product_name || "-"}`,
    `商品類型：${data.product_type || "-"}`,
    `顏色：${data.color || "-"}`,
    `材質：${data.material || "-"}`,
    `版型：${data.fit || "-"}`,
    `商品特色：${data.features || "-"}`,
  ].join("\n");
}

function fillAiFields(data) {
  const productName = document.getElementById("productNameInput");
  const sizeChart = document.getElementById("sizeChartInput");
  const description = document.getElementById("aiDescriptionInput");
  const lineText = document.getElementById("lineGroupTextInput");
  const liveScript = document.getElementById("liveScriptInput");

  lastAiRecognition = data || {};
  if (productName && data.product_name) productName.value = data.product_name;
  if (sizeChart && data.size_chart) sizeChart.value = data.size_chart;
  if (description && data.ai_description) description.value = data.ai_description;
  if (lineText) lineText.value = data.line_group_text || buildLineGroupText();
  if (liveScript && data.live_script) liveScript.value = data.live_script;

  const colorChanged = autoCheckOptions(".variant-color", [data.color, data.features]);
  const specChanged = autoCheckOptions(".other-spec-option", [
    data.product_type,
    data.material,
    data.fit,
    data.features,
  ]);
  if (colorChanged || specChanged) updateVariantRows();
}

function showNameSuggestions(suggestions) {
  const list = document.getElementById("aiNameSuggestionsList");
  const modalElement = document.getElementById("aiNameSuggestionsModal");
  if (!list || !modalElement) return;
  list.innerHTML = "";
  suggestions.forEach((name, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "list-group-item list-group-item-action ai-name-suggestion";
    button.dataset.name = name;
    button.textContent = `${index + 1}. ${name}`;
    list.appendChild(button);
  });
  if (window.bootstrap?.Modal) {
    window.bootstrap.Modal.getOrCreateInstance(modalElement).show();
  }
}

function currentProductName() {
  return document.getElementById("productNameInput")?.value.trim() || "";
}

async function callAiApi(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok || !result.success) {
    throw new Error(result.message || "AI服務暫時無法使用");
  }
  return result.content || "";
}

async function generateGeminiContent(action) {
  const productName = currentProductName();
  if (!productName) {
    setAiStatus("請先輸入商品名稱", "danger");
    return;
  }

  const actionConfig = {
    size_chart: {
      url: window.aiSizeChartUrl,
      title: "AI產生尺寸表",
      targetId: "sizeChartInput",
      payload: { product_name: productName },
    },
    description: {
      url: window.aiProductDescriptionUrl,
      title: "AI產生商品文案",
      targetId: "aiDescriptionInput",
      payload: { product_name: productName },
    },
    line: {
      url: window.aiGroupBuyUrl,
      title: "AI產生LINE團購文",
      targetId: "lineGroupTextInput",
      payload: {
        product_name: productName,
        price: document.getElementById("productPriceInput")?.value || "",
      },
    },
    live: {
      url: window.aiLiveScriptUrl,
      title: "AI產生直播話術",
      targetId: "liveScriptInput",
      payload: { product_name: productName },
    },
  }[action];

  if (!actionConfig?.url) return;

  setAiStatus("AI產生中...", "success");
  try {
    const content = await callAiApi(actionConfig.url, actionConfig.payload);
    const target = document.getElementById(actionConfig.targetId);
    if (target) target.value = content;
    setAiStatus("AI產生成功", "success");
  } catch (error) {
    const message = error.message || "AI服務暫時無法使用";
    setAiStatus(message, "danger");
  }
}

async function analyzeProductImage() {
  const url = window.aiAnalyzeUrl;
  if (!url) return;

  const formData = new FormData();
  const imageInput = document.getElementById("productImageInput");
  const imageError = document.getElementById("productImageError");
  const imageFile = imageInput?.files?.[0];
  if (!imageFile) {
    if (imageError) imageError.textContent = "請先上傳商品圖片";
    setAiStatus("請先上傳商品圖片", "danger");
    return;
  }
  const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
  if (!allowedTypes.includes(imageFile.type)) {
    if (imageError) imageError.textContent = "商品圖片格式僅支援 jpg、jpeg、png、webp";
    setAiStatus("商品圖片格式僅支援 jpg、jpeg、png、webp", "danger");
    return;
  }
  if (imageError) imageError.textContent = "";
  formData.append("image", imageFile);

  setAiStatus("AI辨識中...", "success");

  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.message || "AI辨識失敗");
    }
    fillAiFields(result.data);
    setAiStatus("AI辨識完成", "success");
  } catch (error) {
    setAiStatus(error.message || "AI辨識失敗，請稍後再試。", "danger");
  }
}

async function generateNameSuggestions() {
  const url = window.aiNameSuggestionsUrl;
  if (!url) return;

  const imageInput = document.getElementById("productImageInput");
  const imageError = document.getElementById("productImageError");
  const imageFile = imageInput?.files?.[0];
  if (!imageFile) {
    if (imageError) imageError.textContent = "請先上傳商品圖片";
    setAiStatus("請先上傳商品圖片", "danger");
    return;
  }

  const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
  if (!allowedTypes.includes(imageFile.type)) {
    if (imageError) imageError.textContent = "商品圖片格式僅支援 jpg、jpeg、png、webp";
    setAiStatus("商品圖片格式僅支援 jpg、jpeg、png、webp", "danger");
    return;
  }

  if (imageError) imageError.textContent = "";
  const formData = new FormData();
  formData.append("image", imageFile);
  formData.append("product_name", currentProductName());
  formData.append("recognized_data", JSON.stringify(lastAiRecognition || {}));

  setAiStatus("AI正在重新優化商品名稱...", "success");
  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
    });
    const result = await response.json();
    if (!response.ok || !result.success || !result.suggestions?.length) {
      throw new Error(result.message || "AI服務暫時無法使用");
    }
    showNameSuggestions(result.suggestions.slice(0, 3));
    setAiStatus("已產生商品名稱建議", "success");
  } catch (error) {
    const message = error.message || "AI服務暫時無法使用";
    setAiStatus(message, "danger");
  }
}

function runAiAction(action) {
  if (action === "analyze") {
    analyzeProductImage();
    return;
  }

  if (["size_chart", "description", "line", "live"].includes(action)) {
    generateGeminiContent(action);
    return;
  }

  if (action === "name") {
    generateNameSuggestions();
    return;
  }
}

function initProductHoverPreview() {
  const preview = document.getElementById("productHoverPreview");
  if (!preview) return;

  const previewImage = preview.querySelector("img");
  const movePreview = (event) => {
    const margin = 18;
    const previewSize = Number(preview.dataset.previewSize || 260);
    let left = event.clientX + margin;
    let top = event.clientY + margin;

    if (left + previewSize > window.innerWidth) {
      left = event.clientX - previewSize - margin;
    }
    if (top + previewSize > window.innerHeight) {
      top = event.clientY - previewSize - margin;
    }

    preview.style.left = `${Math.max(8, left)}px`;
    preview.style.top = `${Math.max(8, top)}px`;
  };

  document.addEventListener("pointerover", (event) => {
    const image = event.target.closest(".product-preview-trigger");
    if (!image) return;
    previewImage.src = image.dataset.previewSrc;
    previewImage.alt = image.alt || "";
    preview.classList.add("is-visible");
    movePreview(event);
  });

  document.addEventListener("pointermove", (event) => {
    if (event.target.closest(".product-preview-trigger")) {
      movePreview(event);
    }
  });

  document.addEventListener("pointerout", (event) => {
    const image = event.target.closest(".product-preview-trigger");
    if (!image) return;
    if (!event.relatedTarget || !image.contains(event.relatedTarget)) {
      preview.classList.remove("is-visible");
      previewImage.src = "";
    }
  });
}

function initProductImagePreview() {
  const input = document.getElementById("productImageInput");
  const preview = document.getElementById("productImagePreview");
  const placeholder = document.getElementById("productImagePreviewPlaceholder");
  const imageError = document.getElementById("productImageError");
  if (!input || !preview || !placeholder) return;

  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (!file) {
      preview.classList.add("d-none");
      preview.removeAttribute("src");
      placeholder.classList.remove("d-none");
      if (imageError) imageError.textContent = "";
      return;
    }

    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!allowedTypes.includes(file.type)) {
      preview.classList.add("d-none");
      preview.removeAttribute("src");
      placeholder.classList.remove("d-none");
      if (imageError) imageError.textContent = "商品圖片格式僅支援 jpg、jpeg、png、webp";
      return;
    }

    if (imageError) imageError.textContent = "";
    const reader = new FileReader();
    reader.onload = (event) => {
      preview.src = event.target.result;
      preview.classList.remove("d-none");
      placeholder.classList.add("d-none");
    };
    reader.readAsDataURL(file);
  });
}

function groupBuyItemRow(data) {
  const imageCell = data.image
    ? `<img class="order-product-thumb" src="${data.image}" alt="${data.name}">`
    : '<div class="order-product-thumb order-placeholder-thumb">無圖</div>';
  return `
    <tr data-variant-id="${data.variantId}" data-original-price="${data.price}">
      <td>${imageCell}</td>
      <td class="fw-semibold">${data.sku}<input type="hidden" name="variant_id" value="${data.variantId}"></td>
      <td>${data.name}</td>
      <td>${data.color}</td>
      <td>${data.size}</td>
      <td>${data.supplyMode}<input type="hidden" name="supply_mode_${data.variantId}" value="${data.supplyMode}"></td>
      <td class="text-end">$${Number(data.price || 0).toFixed(0)}</td>
      <td><input class="form-control form-control-sm text-end gb-price" type="number" name="group_price_${data.variantId}" value="${Number(data.price || 0).toFixed(0)}"></td>
      <td><input class="form-control form-control-sm text-end gb-limit" type="number" min="0" name="order_limit_${data.variantId}" value="${data.stock || 0}"></td>
      <td><button class="btn btn-sm btn-outline-danger gb-remove" type="button">移除</button></td>
    </tr>
  `;
}

function initGroupBuyFormTools() {
  const rows = document.getElementById("groupBuyItems");
  if (!rows) return;

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest(".gb-add-product");
    if (addButton) {
      const variantId = addButton.dataset.variantId;
      if (rows.querySelector(`[data-variant-id="${variantId}"]`)) return;
      document.getElementById("emptyGroupBuyItems")?.remove();
      rows.insertAdjacentHTML(
        "beforeend",
        groupBuyItemRow({
          variantId,
          image: addButton.dataset.image,
          sku: addButton.dataset.sku,
          name: addButton.dataset.name,
          color: addButton.dataset.color,
          size: addButton.dataset.size,
          stock: addButton.dataset.stock,
          price: addButton.dataset.price,
          supplyMode: addButton.dataset.supplyMode,
        })
      );
      addButton.closest("tr")?.remove();
      return;
    }

    const removeButton = event.target.closest(".gb-remove");
    if (removeButton) {
      removeButton.closest("tr")?.remove();
      if (!rows.querySelector("tr")) {
        rows.innerHTML = '<tr id="emptyGroupBuyItems"><td colspan="10" class="text-center text-secondary py-3">尚未加入商品。</td></tr>';
      }
      return;
    }

    const batchButton = event.target.closest(".gb-batch");
    if (!batchButton) return;
    const action = batchButton.dataset.action;
    const amount = ["minus", "plus", "limit"].includes(action) ? Number(prompt("請輸入數值", "0") || 0) : 0;
    rows.querySelectorAll("tr[data-variant-id]").forEach((row) => {
      const priceInput = row.querySelector(".gb-price");
      const limitInput = row.querySelector(".gb-limit");
      const originalPrice = Number(row.dataset.originalPrice || 0);
      if (action === "95") priceInput.value = Math.round(originalPrice * 0.95);
      if (action === "90") priceInput.value = Math.round(originalPrice * 0.9);
      if (action === "minus") priceInput.value = Math.max(0, Number(priceInput.value || 0) - amount);
      if (action === "plus") priceInput.value = Math.max(0, Number(priceInput.value || 0) + amount);
      if (action === "reset") priceInput.value = Math.round(originalPrice);
      if (action === "limit") limitInput.value = Math.max(0, amount);
    });
  });
}

document.addEventListener("change", (event) => {
  if (event.target.matches(".variant-color, .variant-size")) {
    updateVariantRows();
  }
});

document.addEventListener("click", async (event) => {
  const copyButton = event.target.closest(".copy-btn");
  if (copyButton) {
    await navigator.clipboard.writeText(copyButton.dataset.copy || "");
    const original = copyButton.textContent;
    copyButton.textContent = "已複製";
    setTimeout(() => {
      copyButton.textContent = original;
    }, 1200);
    return;
  }

  const aiButton = event.target.closest(".ai-action");
  if (aiButton) {
    runAiAction(aiButton.dataset.aiAction);
  }

  const nameSuggestion = event.target.closest(".ai-name-suggestion");
  if (nameSuggestion) {
    const productName = document.getElementById("productNameInput");
    if (productName) productName.value = nameSuggestion.dataset.name || nameSuggestion.textContent.trim();
    const modalElement = document.getElementById("aiNameSuggestionsModal");
    if (modalElement && window.bootstrap?.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modalElement).hide();
    }
    setAiStatus("已套用商品名稱", "success");
  }

});

function gbVariantMarkup(data, price) {
  return `
    <div class="col-sm-6 col-lg-4 gb-spec-item" data-variant-id="${data.variantId}">
      <input type="hidden" name="variant_id" value="${data.variantId}">
      <input type="hidden" name="supply_mode_${data.variantId}" value="${data.supplyMode}">
      <input class="gb-price-hidden" type="hidden" name="group_price_${data.variantId}" value="${Number(price || 0).toFixed(0)}">
      <div class="border rounded p-2 h-100">
        <div class="d-flex justify-content-between gap-2">
          <span class="fw-semibold">${data.size || "-"}</span>
          <span class="text-secondary small">目前庫存 ${data.stock || 0}</span>
        </div>
        <label class="form-label small mt-2 mb-1">可下單數量</label>
        <input class="form-control form-control-sm text-end gb-limit" type="number" min="0" name="order_limit_${data.variantId}" value="${data.stock || 0}">
      </div>
    </div>
  `;
}

function gbProductCardMarkup(data) {
  const imageCell = data.image
    ? `<img class="order-product-thumb" src="${data.image}" alt="${data.name}">`
    : '<div class="order-product-thumb order-placeholder-thumb">無圖</div>';
  return `
    <div class="group-buy-product-card border rounded p-3 mb-3" data-product-id="${data.productId}" data-original-price="${data.price || 0}">
      <div class="d-flex flex-column flex-lg-row gap-3">
        <div>${imageCell}</div>
        <div class="flex-grow-1">
          <div class="d-flex flex-wrap justify-content-between gap-3">
            <div>
              <div class="fw-semibold">${data.name}</div>
              <div class="text-secondary small">商品編號：${data.sku}</div>
              <div class="text-secondary small">供貨模式：${data.supplyMode}</div>
            </div>
            <div class="text-lg-end">
              <div class="small text-secondary">原售價</div>
              <div class="fw-semibold">$${Number(data.price || 0).toFixed(0)}</div>
            </div>
            <div style="min-width: 160px;">
              <label class="form-label small mb-1">團購價</label>
              <input class="form-control form-control-sm text-end gb-product-price" type="number" min="0" value="${Number(data.price || 0).toFixed(0)}">
            </div>
            <div class="text-lg-end">
              <div class="small text-secondary">本商品可下單總數</div>
              <div class="fw-semibold gb-product-limit-total">0</div>
            </div>
            <div>
              <button class="btn btn-sm btn-outline-danger gb-remove-product" type="button">移除整個商品</button>
            </div>
          </div>
          <div class="gb-spec-list mt-3"></div>
        </div>
      </div>
    </div>
  `;
}

function gbEnsureColorGroup(card, color) {
  const list = card.querySelector(".gb-spec-list");
  let group = Array.from(list.querySelectorAll(".gb-color-group")).find((item) => item.dataset.color === color);
  if (group) return group;
  group = document.createElement("div");
  group.className = "gb-color-group border-top pt-2 mt-2";
  group.dataset.color = color;
  group.innerHTML = `<div class="fw-semibold mb-2">${color}</div><div class="row g-2"></div>`;
  list.appendChild(group);
  return group;
}

function gbSyncProductCard(card) {
  const price = Math.max(0, Number(card.querySelector(".gb-product-price")?.value || 0));
  let totalLimit = 0;
  card.querySelectorAll(".gb-price-hidden").forEach((input) => {
    input.value = Math.round(price);
  });
  card.querySelectorAll(".gb-limit").forEach((input) => {
    totalLimit += Math.max(0, Number(input.value || 0));
  });
  const total = card.querySelector(".gb-product-limit-total");
  if (total) total.textContent = String(totalLimit);
}

function gbShowEmptyItems(container) {
  if (!container.querySelector(".group-buy-product-card")) {
    container.innerHTML = '<div id="emptyGroupBuyItems" class="text-center text-secondary py-3 border rounded">尚未加入商品。</div>';
  }
}

function gbAddVariant(container, data) {
  if (container.querySelector(`[data-variant-id="${data.variantId}"]`)) return;
  document.getElementById("emptyGroupBuyItems")?.remove();
  let card = container.querySelector(`.group-buy-product-card[data-product-id="${data.productId}"]`);
  if (!card) {
    container.insertAdjacentHTML("beforeend", gbProductCardMarkup(data));
    card = container.querySelector(`.group-buy-product-card[data-product-id="${data.productId}"]`);
  }
  const price = card.querySelector(".gb-product-price")?.value || data.price || 0;
  const colorGroup = gbEnsureColorGroup(card, data.color || "-");
  colorGroup.querySelector(".row").insertAdjacentHTML("beforeend", gbVariantMarkup(data, price));
  gbSyncProductCard(card);
}

function initGroupBuyFormTools() {
  const items = document.getElementById("groupBuyItems");
  if (!items) return;
  items.querySelectorAll(".group-buy-product-card").forEach(gbSyncProductCard);

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest(".gb-add-product");
    if (addButton) {
      gbAddVariant(items, {
        productId: addButton.dataset.productId,
        variantId: addButton.dataset.variantId,
        image: addButton.dataset.image,
        sku: addButton.dataset.sku,
        name: addButton.dataset.name,
        color: addButton.dataset.color,
        size: addButton.dataset.size,
        stock: addButton.dataset.stock,
        price: addButton.dataset.price,
        supplyMode: addButton.dataset.supplyMode,
      });
      addButton.closest("tr")?.remove();
      return;
    }

    const removeProduct = event.target.closest(".gb-remove-product");
    if (removeProduct) {
      removeProduct.closest(".group-buy-product-card")?.remove();
      gbShowEmptyItems(items);
      return;
    }

    const batchButton = event.target.closest(".gb-batch");
    if (!batchButton) return;
    const action = batchButton.dataset.action;
    const amount = ["minus", "plus", "limit"].includes(action) ? Number(prompt("請輸入數值", "0") || 0) : 0;
    items.querySelectorAll(".group-buy-product-card").forEach((card) => {
      const priceInput = card.querySelector(".gb-product-price");
      const originalPrice = Number(card.dataset.originalPrice || 0);
      if (action === "95") priceInput.value = Math.round(originalPrice * 0.95);
      if (action === "90") priceInput.value = Math.round(originalPrice * 0.9);
      if (action === "minus") priceInput.value = Math.max(0, Number(priceInput.value || 0) - amount);
      if (action === "plus") priceInput.value = Math.max(0, Number(priceInput.value || 0) + amount);
      if (action === "reset") priceInput.value = Math.round(originalPrice);
      if (action === "limit") {
        card.querySelectorAll(".gb-limit").forEach((limitInput) => {
          limitInput.value = Math.max(0, amount);
        });
      }
      gbSyncProductCard(card);
    });
  });

  document.addEventListener("input", (event) => {
    const target = event.target.closest(".gb-product-price, .gb-limit");
    if (!target) return;
    const card = target.closest(".group-buy-product-card");
    if (card) gbSyncProductCard(card);
  });
}

function updatePublicGroupBuyTotals() {
  let totalQuantity = 0;
  let totalAmount = 0;
  document.querySelectorAll(".public-gb-product-card").forEach((card) => {
    let productQuantity = 0;
    let productAmount = 0;
    card.querySelectorAll(".public-gb-quantity").forEach((input) => {
      const quantity = Math.max(0, Number(input.value || 0));
      const price = Math.max(0, Number(input.dataset.price || 0));
      productQuantity += quantity;
      productAmount += quantity * price;
    });
    totalQuantity += productQuantity;
    totalAmount += productAmount;
    const count = card.querySelector(".public-gb-product-count");
    const subtotal = card.querySelector(".public-gb-product-subtotal");
    if (count) count.textContent = String(productQuantity);
    if (subtotal) subtotal.textContent = `$${Math.round(productAmount)}`;
  });
  const totalQuantityEl = document.getElementById("publicGbTotalQuantity");
  const totalAmountEl = document.getElementById("publicGbTotalAmount");
  if (totalQuantityEl) totalQuantityEl.textContent = String(totalQuantity);
  if (totalAmountEl) totalAmountEl.textContent = `$${Math.round(totalAmount)}`;
}

function initPublicGroupBuyTotals() {
  if (!document.querySelector(".public-gb-quantity")) return;
  updatePublicGroupBuyTotals();
  document.addEventListener("input", (event) => {
    if (event.target.matches(".public-gb-quantity")) {
      updatePublicGroupBuyTotals();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  updateVariantRows();
  initProductHoverPreview();
  initProductImagePreview();
  initGroupBuyFormTools();
  initPublicGroupBuyTotals();
});
