(function () {
  const modal = document.getElementById("wechat-modal");
  const triggers = document.querySelectorAll('a[href="#wechat"]');

  if (!modal || triggers.length === 0) {
    return;
  }

  const closeButton = modal.querySelector(".wechat-modal__close");
  const copyButton = modal.querySelector(".wechat-modal__copy");
  const hint = modal.querySelector(".wechat-modal__hint");

  function openModal(event) {
    event.preventDefault();
    modal.classList.add("is-visible");
    modal.setAttribute("aria-hidden", "false");
    if (copyButton) {
      copyButton.focus();
    } else if (closeButton) {
      closeButton.focus();
    }
  }

  function closeModal() {
    modal.classList.remove("is-visible");
    modal.setAttribute("aria-hidden", "true");
    if (hint) {
      hint.textContent = "Click to copy";
    }
  }

  function fallbackCopy(text) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }

  async function copyWechatId() {
    if (!copyButton) {
      return;
    }

    const wechatId = copyButton.dataset.copyText;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(wechatId);
      } else {
        fallbackCopy(wechatId);
      }
      if (hint) {
        hint.textContent = "Copied!";
      }
    } catch (error) {
      if (hint) {
        hint.textContent = "Copy failed — please copy manually.";
      }
    }
  }

  triggers.forEach((trigger) => {
    trigger.addEventListener("click", openModal);
  });

  if (closeButton) {
    closeButton.addEventListener("click", closeModal);
  }

  if (copyButton) {
    copyButton.addEventListener("click", copyWechatId);
  }

  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal.classList.contains("is-visible")) {
      closeModal();
    }
  });
})();
