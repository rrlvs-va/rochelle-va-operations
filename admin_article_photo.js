(() => {
  'use strict';

  let existingPhoto = '';
  let photoFile = null;
  let photoRemoved = false;
  let photoObjectUrl = '';

  const $ = id => document.getElementById(id);
  const imageUrl = path => path ? `${window.SITE_ORIGIN || ''}/blog/${path}` : '';

  function currentPhotoUrl() {
    if (photoObjectUrl) return photoObjectUrl;
    if (!photoRemoved && existingPhoto) {
      const siteOrigin = typeof SITE_ORIGIN === 'string' ? SITE_ORIGIN : '';
      return siteOrigin ? `${siteOrigin}/blog/${existingPhoto}` : `/blog/${existingPhoto}`;
    }
    return '';
  }

  function injectStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .actual-photo-preview{margin:28px 0 4px;padding-top:20px;border-top:1px solid #ded3c8}
      .actual-photo-preview[hidden]{display:none}
      .actual-photo-preview img{display:block;max-width:100%;width:auto;height:auto;margin:0 auto;border:1px solid #d8cec4;background:#fff}
      .actual-photo-preview-note{margin-top:8px;color:#8a7467;font-size:.72rem;text-align:center}
    `;
    document.head.appendChild(style);
  }

  function injectField() {
    const body = $('body');
    if (!body) return;
    const bodyField = body.closest('.field');
    if (!bodyField || $('actualPhotoInput')) return;

    const field = document.createElement('div');
    field.className = 'field full';
    field.innerHTML = `
      <div class="image-block">
        <strong>Article photo (optional)</strong>
        <input id="actualPhotoInput" type="file" accept="image/jpeg,image/png,image/webp">
        <div class="upload-row">
          <span class="upload-status" id="actualPhotoStatus">No article photo selected.</span>
          <button class="small-btn" id="removeActualPhoto" type="button" hidden>Remove photo</button>
        </div>
        <div class="help">This is a normal photo inside the article, not a cover. It appears after the article text at its original aspect ratio with no cropping. Large images only scale down enough to fit the page.</div>
      </div>`;
    bodyField.insertAdjacentElement('afterend', field);

    $('actualPhotoInput').addEventListener('change', choosePhoto);
    $('removeActualPhoto').addEventListener('click', removePhoto);
  }

  function injectPreview() {
    const bodyPreview = $('bodyPreview');
    if (!bodyPreview || $('actualPhotoPreviewWrap')) return;

    const wrap = document.createElement('figure');
    wrap.id = 'actualPhotoPreviewWrap';
    wrap.className = 'actual-photo-preview';
    wrap.hidden = true;
    wrap.innerHTML = `
      <img id="actualPhotoPreview" alt="Article photo preview">
      <figcaption class="actual-photo-preview-note">Article photo · full image, uncropped</figcaption>`;
    bodyPreview.insertAdjacentElement('afterend', wrap);
  }

  function refreshPreview() {
    const url = currentPhotoUrl();
    const wrap = $('actualPhotoPreviewWrap');
    const img = $('actualPhotoPreview');
    const remove = $('removeActualPhoto');
    if (wrap && img) {
      if (url) {
        img.src = url;
        wrap.hidden = false;
      } else {
        img.removeAttribute('src');
        wrap.hidden = true;
      }
    }
    if (remove) remove.hidden = !url;
  }

  function choosePhoto(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      alert('Please choose a JPEG, PNG, or WebP image.');
      event.target.value = '';
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert('Article photos must be 5 MB or smaller.');
      event.target.value = '';
      return;
    }

    if (photoObjectUrl) URL.revokeObjectURL(photoObjectUrl);
    photoObjectUrl = URL.createObjectURL(file);
    photoFile = file;
    photoRemoved = false;
    $('actualPhotoStatus').textContent = `${file.name} · ready to save`;
    refreshPreview();
  }

  function removePhoto() {
    if (photoObjectUrl) {
      URL.revokeObjectURL(photoObjectUrl);
      photoObjectUrl = '';
    }
    photoFile = null;
    existingPhoto = '';
    photoRemoved = true;
    if ($('actualPhotoInput')) $('actualPhotoInput').value = '';
    if ($('actualPhotoStatus')) $('actualPhotoStatus').textContent = 'No article photo selected.';
    refreshPreview();
  }

  async function uploadPhoto(file, slug) {
    const form = new FormData();
    form.append('image', file);
    form.append('slug', `${slug || 'draft'}-photo`);
    const response = await fetch('/admin/api/images/upload', {
      method: 'POST',
      headers: {'X-CSRF-Token': typeof CSRF === 'string' ? CSRF : ''},
      body: form,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Article photo upload failed.');
    return data.path || '';
  }

  function hookEditorFunctions() {
    const originalPayload = window.payload;
    if (typeof originalPayload === 'function') {
      window.payload = function () {
        const value = originalPayload();
        value.article_photo = photoRemoved ? '' : existingPhoto;
        return value;
      };
    }

    const originalPrepareImages = window.prepareImages;
    if (typeof originalPrepareImages === 'function') {
      window.prepareImages = async function (value) {
        let result = await originalPrepareImages(value);
        if (photoFile) {
          const notice = $('notice');
          if (notice) notice.textContent = 'Uploading article photo…';
          result.article_photo = await uploadPhoto(photoFile, result.slug || 'draft');
          existingPhoto = result.article_photo;
          photoFile = null;
          photoRemoved = false;
          if (photoObjectUrl) {
            URL.revokeObjectURL(photoObjectUrl);
            photoObjectUrl = '';
          }
          if ($('actualPhotoStatus')) $('actualPhotoStatus').textContent = 'Existing article photo';
          refreshPreview();
        }
        return result;
      };
    }
  }

  async function loadExistingPhoto() {
    const edit = new URLSearchParams(location.search).get('edit');
    if (!edit) {
      refreshPreview();
      return;
    }
    try {
      const response = await fetch(`/admin/api/articles?cb=${Date.now()}`, {
        cache: 'no-store',
        headers: {'Cache-Control': 'no-cache'},
      });
      if (!response.ok) return;
      const data = await response.json();
      const article = (data.articles || []).find(item => item.slug === edit);
      if (!article) return;
      existingPhoto = article.article_photo || '';
      photoRemoved = false;
      if (existingPhoto && $('actualPhotoStatus')) $('actualPhotoStatus').textContent = 'Existing article photo';
      refreshPreview();
    } catch (_) {
      // The core editor remains usable even if this optional preview lookup fails.
    }
  }

  function init() {
    injectStyles();
    injectField();
    injectPreview();
    hookEditorFunctions();
    loadExistingPhoto();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }

  window.addEventListener('beforeunload', () => {
    if (photoObjectUrl) URL.revokeObjectURL(photoObjectUrl);
  });
})();
