(() => {
  "use strict";

  const FINISHES = {
    raw: {
      name: "Raw", price: 129, process: "Brushed, 320 grit",
      desc: "Bead-blasted, then brushed by hand around the circumference. The metal exactly as it leaves the press.",
    },
    obsidian: {
      name: "Obsidian", price: 159, process: "DLC coating, 2 µm",
      desc: "A diamond-like carbon coating fused to the surface. Near-black, harder than the titanium beneath it, and shrugs off keys in a gym bag.",
    },
    bronze: {
      name: "Bronze", price: 149, process: "Anodized at 16 V",
      desc: "Grown, not painted: sixteen volts builds an oxide layer thin enough to glow a warm, deep gold.",
    },
    aurora: {
      name: "Aurora", price: 149, process: "Anodized at 30 V",
      desc: "Thirty volts gives a thicker oxide layer and a cold, clear blue that shifts toward violet at the edges.",
    },
  };
  const SIZES = { 500: { label: "500 ml", delta: -20 }, 750: { label: "750 ml", delta: 0 }, 1000: { label: "1 L", delta: 25 } };
  const FREE_SHIP = 150;
  const STORE_KEY = "ti22-bag";

  const $ = (sel) => document.querySelector(sel);
  const money = (n) => "$" + n.toLocaleString("en-US");
  const img = (finish) => `assets/img/shaker-${finish}.webp`;

  // Preload colourway renders so swatch changes are instant.
  Object.keys(FINISHES).forEach((f) => { const i = new Image(); i.src = img(f); });

  /* ---------------------------------------------------------- configurator */
  const form = $("#buy-form");
  const buyImg = $("#buy-img");
  const qtyInput = $("#qty");

  const current = () => {
    const finish = form.querySelector('input[name="finish"]:checked').value;
    const size = form.querySelector('input[name="size"]:checked').value;
    const qty = clampQty(parseInt(qtyInput.value, 10));
    return { finish, size, qty, unit: FINISHES[finish].price + SIZES[size].delta };
  };
  const clampQty = (n) => Math.min(9, Math.max(1, Number.isFinite(n) ? n : 1));

  let shownFinish = "raw";
  function renderConfig() {
    const c = current();
    const f = FINISHES[c.finish];
    $("#buy-finish-name").textContent = f.name;
    $("#buy-price").textContent = money(c.unit);
    $("#buy-ship").textContent = c.unit >= FREE_SHIP ? "Free shipping" : `Free shipping over ${money(FREE_SHIP)}`;
    $("#buy-desc").textContent = f.desc;
    $("#finish-process").textContent = f.process;
    if (c.finish !== shownFinish) {
      shownFinish = c.finish;
      buyImg.classList.add("swap");
      setTimeout(() => {
        buyImg.src = img(c.finish);
        buyImg.alt = `Ti22 shaker in ${f.name} finish`;
        buyImg.classList.remove("swap");
      }, 180);
    }
  }
  form.addEventListener("change", renderConfig);
  $("#qty-dec").addEventListener("click", () => { qtyInput.value = clampQty(+qtyInput.value - 1); });
  $("#qty-inc").addEventListener("click", () => { qtyInput.value = clampQty(+qtyInput.value + 1); });
  qtyInput.addEventListener("change", () => { qtyInput.value = clampQty(parseInt(qtyInput.value, 10)); });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const c = current();
    addToBag(c.finish, c.size, c.qty);
    toast(`${FINISHES[c.finish].name} ${SIZES[c.size].label} added to bag`);
    bumpCount();
  });

  /* ---------------------------------------------------------- bag */
  let bag = load();

  function load() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter((l) => FINISHES[l.finish] && SIZES[l.size]) : [];
    } catch { return []; }
  }
  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(bag)); } catch { /* storage unavailable */ }
  }
  const unitPrice = (l) => FINISHES[l.finish].price + SIZES[l.size].delta;

  function addToBag(finish, size, qty) {
    const hit = bag.find((l) => l.finish === finish && l.size === size);
    if (hit) hit.qty = Math.min(9, hit.qty + qty);
    else bag.push({ finish, size, qty });
    save(); renderBag();
  }

  function renderBag() {
    const list = $("#bag-items");
    list.textContent = "";
    let count = 0, subtotal = 0;
    bag.forEach((l, i) => {
      count += l.qty;
      subtotal += unitPrice(l) * l.qty;
      const li = document.createElement("li");
      li.className = "bag-item";
      li.innerHTML = `
        <img src="${img(l.finish)}" alt="" width="72" height="90">
        <div>
          <h3>Ti22 Shaker, ${FINISHES[l.finish].name}</h3>
          <p class="meta">${SIZES[l.size].label} &middot; ${money(unitPrice(l))}</p>
          <div class="mini-qty" role="group" aria-label="Quantity">
            <button type="button" data-act="dec" data-i="${i}" aria-label="Decrease quantity">&minus;</button>
            <span>${l.qty}</span>
            <button type="button" data-act="inc" data-i="${i}" aria-label="Increase quantity">+</button>
          </div>
        </div>
        <div class="line-price">
          <span>${money(unitPrice(l) * l.qty)}</span>
          <button type="button" class="remove" data-act="rm" data-i="${i}">Remove</button>
        </div>`;
      list.appendChild(li);
    });
    $("#bag-count").textContent = count;
    $("#bag-subtotal").textContent = money(subtotal);
    $("#bag-empty").hidden = bag.length > 0;
    $("#checkout").disabled = bag.length === 0;
    const left = FREE_SHIP - subtotal;
    $("#bag-ship-text").textContent = left > 0
      ? `Add ${money(left)} more for free shipping`
      : "Your order ships free";
    $("#bag-meter").style.width = Math.min(100, (subtotal / FREE_SHIP) * 100) + "%";
    $("#checkout-msg").textContent = "";
  }

  $("#bag-items").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const l = bag[+b.dataset.i];
    if (!l) return;
    if (b.dataset.act === "inc") l.qty = Math.min(9, l.qty + 1);
    if (b.dataset.act === "dec") l.qty -= 1;
    if (b.dataset.act === "rm" || l.qty < 1) bag.splice(+b.dataset.i, 1);
    save(); renderBag();
  });

  // Checkout is not wired to a payment provider yet (Stripe / Shopify go here).
  $("#checkout").addEventListener("click", () => {
    $("#checkout-msg").textContent = "Checkout isn't connected yet. Your bag is saved on this device.";
  });

  /* ---------------------------------------------------------- drawer */
  const drawer = $("#bag"), scrim = $("#scrim"), opener = $("#bag-open");
  function openBag() {
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    opener.setAttribute("aria-expanded", "true");
    scrim.hidden = false;
    document.body.style.overflow = "hidden";
    setTimeout(() => $("#bag-close").focus(), 50);
  }
  function closeBag() {
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    opener.setAttribute("aria-expanded", "false");
    scrim.hidden = true;
    document.body.style.overflow = "";
    opener.focus();
  }
  opener.addEventListener("click", openBag);
  $("#bag-close").addEventListener("click", closeBag);
  scrim.addEventListener("click", closeBag);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && drawer.classList.contains("open")) closeBag(); });

  /* ---------------------------------------------------------- small bits */
  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.innerHTML = "";
    const span = document.createElement("span");
    span.textContent = msg + " ";
    const view = document.createElement("button");
    view.type = "button";
    view.textContent = "View bag";
    view.style.cssText = "border:0;background:none;color:inherit;text-decoration:underline;cursor:pointer;font-weight:600;padding:0;margin-left:6px";
    view.addEventListener("click", openBag);
    t.append(span, view);
    t.style.pointerEvents = "auto";
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.classList.remove("show"); t.style.pointerEvents = "none"; }, 3200);
  }
  function bumpCount() {
    const c = $("#bag-count");
    c.classList.remove("bump"); void c.offsetWidth; c.classList.add("bump");
  }

  // Newsletter: validate in the page; connect to your email provider here.
  $("#newsletter").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#email"), msg = $("#newsletter-msg");
    if (!input.checkValidity() || !input.value) {
      msg.textContent = "Enter an email address like name@example.com.";
      input.focus();
      return;
    }
    msg.textContent = `Thanks. We'll write to ${input.value} when a new finish ships.`;
    input.value = "";
  });

  renderConfig();
  renderBag();
})();
