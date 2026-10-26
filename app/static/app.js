/* B站优质视频案例库 — 前端逻辑（收藏与备注存于 localStorage） */
(function () {
  "use strict";

  var FAV_KEY = "bili.favorites.v1";
  var NOTE_KEY = "bili.notes.v1";
  var memory = {};
  var lastItems = {};
  var controller = null;

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- 本地存储（被禁用时退回内存） ---------- */
  function readJSON(key, fallback) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return Object.prototype.hasOwnProperty.call(memory, key) ? memory[key] : fallback;
    }
  }

  function writeJSON(key, value) {
    memory[key] = value;
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 忽略 */ }
  }

  function getFavorites() {
    var v = readJSON(FAV_KEY, []);
    return Array.isArray(v) ? v : [];
  }

  function isFavorite(bvid) {
    return getFavorites().some(function (f) { return f.bvid === bvid; });
  }

  function snapshot(item) {
    return {
      bvid: item.bvid,
      title: item.title,
      author_name: item.author_name,
      cover_url: item.cover_url,
      pubdate_str: item.pubdate_str,
      duration_str: item.duration_str,
      view_str: item.view_str,
      like_str: item.like_str,
      favorite_str: item.favorite_str,
      reply_str: item.reply_str,
      quality_score: item.quality_score,
      data_complete: item.data_complete,
      bili_url: item.bili_url,
      savedAt: Date.now()
    };
  }

  function addFavorite(item) {
    var list = getFavorites().filter(function (f) { return f.bvid !== item.bvid; });
    list.unshift(snapshot(item));
    writeJSON(FAV_KEY, list);
  }

  function removeFavorite(bvid) {
    writeJSON(FAV_KEY, getFavorites().filter(function (f) { return f.bvid !== bvid; }));
  }

  function getNotes() {
    var v = readJSON(NOTE_KEY, {});
    return v && typeof v === "object" ? v : {};
  }

  function saveNote(bvid, text) {
    var notes = getNotes();
    notes[bvid] = text;
    writeJSON(NOTE_KEY, notes);
  }

  /* ---------- 提示 ---------- */
  var toastTimer = null;
  function toast(msg, isError) {
    var el = $("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast show" + (isError ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = "toast"; }, 2400);
  }

  /* ---------- 卡片渲染 ---------- */
  function scoreBadge(item) {
    if (item.data_complete === 0 || item.data_complete === false) {
      return '<span class="score gray">数据不全</span>';
    }
    if (item.quality_score == null) {
      return '<span class="score gray">数据不全</span>';
    }
    return '<span class="score">' + Math.round(item.quality_score) + " 分</span>";
  }

  function cardHTML(item, options) {
    var opts = options || {};
    var faved = isFavorite(item.bvid);
    var action = opts.removable
      ? '<button class="icon-btn js-unfav" data-bvid="' + esc(item.bvid) + '" title="取消收藏">✕</button>'
      : '<button class="icon-btn js-fav' + (faved ? " on" : "") + '" data-bvid="' + esc(item.bvid) +
        '" title="' + (faved ? "取消收藏" : "收藏") + '">' + (faved ? "★" : "☆") + "</button>";

    return (
      '<article class="card">' +
        '<a class="card-cover" href="/video/' + esc(item.bvid) + '" tabindex="-1" aria-hidden="true">' +
          (item.cover_url
            ? '<img src="' + esc(item.cover_url) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display=\'none\'">'
            : "") +
          scoreBadge(item) +
          (item.duration_str ? '<span class="duration">' + esc(item.duration_str) + "</span>" : "") +
        "</a>" +
        '<div class="card-body">' +
          '<a class="card-title" href="/video/' + esc(item.bvid) + '">' + esc(item.title) + "</a>" +
          '<div class="card-meta">' + esc(item.author_name) + " · " + esc(item.pubdate_str) + "</div>" +
          '<div class="card-metrics">' +
            "<span>▶ " + esc(item.view_str || "0") + "</span>" +
            "<span>赞 " + esc(item.like_str || "0") + "</span>" +
            "<span>藏 " + esc(item.favorite_str || "0") + "</span>" +
          "</div>" +
          '<div class="card-actions">' +
            '<a class="text-link" href="' + esc(item.bili_url) + '" target="_blank" rel="noopener">去B站</a>' +
            action +
          "</div>" +
        "</div>" +
      "</article>"
    );
  }

  function renderCards(box, items, options) {
    if (!box) return;
    box.innerHTML = items.map(function (it) { return cardHTML(it, options); }).join("");
  }

  function showSkeleton(box, count) {
    if (!box) return;
    var one = '<div class="card skeleton">' +
      '<div class="sk-cover shimmer"></div>' +
      '<div class="sk-line w80 shimmer"></div>' +
      '<div class="sk-line w60 shimmer"></div>' +
      "</div>";
    var html = "";
    for (var i = 0; i < count; i++) html += one;
    box.innerHTML = html;
  }

  /* ---------- 搜索 ---------- */
  function doSearch() {
    var input = $("keyword");
    var status = $("status");
    var box = $("results");
    var btn = $("btn-search");
    if (!input || !status || !box) return;

    var keyword = input.value.trim();
    if (!keyword) {
      status.textContent = "先输入一个关键词";
      status.className = "status error";
      input.focus();
      return;
    }

    if (controller) controller.abort();
    controller = new AbortController();

    status.className = "status";
    status.textContent = "正在抓取 B站 数据，首次搜索约需 5–10 秒…";
    box.innerHTML = "";
    showSkeleton(box, 6);
    var hints = $("hints");
    if (hints) hints.remove();
    if (btn) { btn.disabled = true; btn.textContent = "抓取中…"; }

    fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword: keyword,
        time_range: $("time_range") ? $("time_range").value : "all",
        sort: $("sort") ? $("sort").value : "quality"
      }),
      signal: controller.signal
    })
      .then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (data) {
          return { resp: resp, data: data };
        });
      })
      .then(function (out) {
        var data = out.data;
        if (out.resp.status === 429) {
          status.className = "status error";
          status.textContent = data.detail || "搜索太频繁了，请稍后再试";
          box.innerHTML = "";
          return;
        }
        if (!data.ok) {
          status.className = "status error";
          status.textContent = data.error || "抓取失败，请稍后重试";
          box.innerHTML = "";
          return;
        }
        if (!data.items || !data.items.length) {
          status.className = "status";
          status.textContent = "没有找到相关视频，换个关键词或放宽时间范围试试";
          box.innerHTML = '<div class="empty"><h2>没有结果</h2><p>试试更宽泛的关键词，或把时间范围改成「全部时间」。</p></div>';
          return;
        }
        lastItems = {};
        data.items.forEach(function (it) { lastItems[it.bvid] = it; });
        status.className = "status";
        status.textContent = "共 " + data.total + " 条 · " + (data.cached ? "来自缓存" : "实时抓取");
        renderCards(box, data.items);
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") return;
        status.className = "status error";
        status.textContent = "请求失败，请检查网络后重试";
        box.innerHTML = "";
      })
      .then(function () {
        if (btn) { btn.disabled = false; btn.textContent = "搜索"; }
      });
  }

  function bindSearchPage() {
    var form = $("search-form");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        doSearch();
      });
    }
    var chips = $("chips");
    if (chips) {
      chips.addEventListener("click", function (e) {
        var chip = e.target.closest(".chip");
        if (!chip) return;
        var input = $("keyword");
        if (!input) return;
        input.value = chip.getAttribute("data-kw") || chip.textContent;
        doSearch();
      });
    }

    // 支持 /?q=关键词 直链，方便把搜索结果分享给别人
    var params = new URLSearchParams(window.location.search);
    var initial = params.get("q");
    if (initial) {
      var kw = $("keyword");
      if (kw) {
        kw.value = initial;
        doSearch();
      }
    }
  }

  /* ---------- 详情页 ---------- */
  function bindVideoPage() {
    var favBtn = $("btn-fav");
    var bvid = favBtn ? favBtn.getAttribute("data-bvid") : null;
    if (favBtn && bvid) {
      var syncButton = function () {
        var on = isFavorite(bvid);
        favBtn.textContent = on ? "★ 已收藏" : "☆ 收藏";
        favBtn.className = "btn" + (on ? " is-fav" : "");
      };
      syncButton();
      favBtn.addEventListener("click", function () {
        if (isFavorite(bvid)) {
          removeFavorite(bvid);
          toast("已取消收藏");
        } else {
          fetch("/api/video/" + encodeURIComponent(bvid))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data && data.ok && data.video) addFavorite(data.video);
              else addFavorite({ bvid: bvid, title: document.title, bili_url: "https://www.bilibili.com/video/" + bvid });
              toast("已收藏，可在「我的案例」找到");
            })
            .catch(function () {
              toast("收藏失败，请重试", true);
            });
        }
        syncButton();
      });
    }

    var note = $("note");
    var saveBtn = $("btn-save-note");
    if (note && bvid) {
      note.value = getNotes()[bvid] || "";
      var state = $("note-state");
      var stamp = function () {
        if (!state) return;
        var d = new Date();
        state.textContent = "已保存 " + ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
      };
      var timer = null;
      var persist = function () {
        saveNote(bvid, note.value);
        stamp();
      };
      note.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(persist, 700);
      });
      if (saveBtn) {
        saveBtn.addEventListener("click", function () {
          clearTimeout(timer);
          persist();
          toast("备注已保存到本机");
        });
      }
    }
  }

  /* ---------- 我的案例 ---------- */
  function bindFavoritesPage() {
    var box = $("fav-grid");
    if (!box) return;
    var empty = $("fav-empty");
    var count = $("fav-count");

    var render = function () {
      var items = getFavorites();
      if (!items.length) {
        box.innerHTML = "";
        if (empty) empty.hidden = false;
        if (count) count.textContent = "";
        return;
      }
      if (empty) empty.hidden = true;
      if (count) count.textContent = "共 " + items.length + " 条";
      renderCards(box, items, { removable: true });
    };

    render();
    box.addEventListener("click", function (e) {
      var btn = e.target.closest(".js-unfav");
      if (!btn) return;
      removeFavorite(btn.getAttribute("data-bvid"));
      render();
      toast("已取消收藏");
    });
  }

  /* ---------- 全局：搜索卡片上的收藏按钮 ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-fav");
    if (!btn) return;
    var bvid = btn.getAttribute("data-bvid");
    if (!bvid) return;
    if (isFavorite(bvid)) {
      removeFavorite(bvid);
      toast("已取消收藏");
    } else {
      var item = lastItems[bvid];
      if (item) addFavorite(item);
      toast(item ? "已收藏，可在「我的案例」找到" : "收藏失败，请刷新后重试", !item);
    }
    document.querySelectorAll('.js-fav[data-bvid="' + bvid + '"]').forEach(function (b) {
      var on = isFavorite(bvid);
      b.className = "icon-btn js-fav" + (on ? " on" : "");
      b.textContent = on ? "★" : "☆";
      b.title = on ? "取消收藏" : "收藏";
    });
  });

  document.addEventListener("DOMContentLoaded", function () {
    bindSearchPage();
    bindVideoPage();
    bindFavoritesPage();
  });
})();
