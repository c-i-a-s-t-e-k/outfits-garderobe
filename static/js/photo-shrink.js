/*
 * Shrinks a large photo in the browser before the add-garment form is sent.
 *
 * A camera photo is 3–5 MB; over mobile data that upload alone eats the
 * five-second budget. The server normalizes every photo anyway, so this only
 * sends it something already close to what it will store.
 *
 * Progressive enhancement, never a new way to fail: whenever anything here
 * does not work — a browser that cannot decode HEIC, memory pressure, a
 * missing API — the original file stays selected and the server path, which
 * works with JavaScript off, handles it.
 *
 * Acts on file inputs marked with data-shrink-photo, and writes progress into
 * the [data-shrink-status] element of the same form.
 */
(function () {
  'use strict';

  // Keep in step with privatemedia/processing.py (MAX_EDGE_PX, JPEG_QUALITY).
  var MAX_EDGE_PX = 1600;
  var JPEG_QUALITY = 0.85;
  // A photo already this small in both senses is not worth re-encoding.
  var UNTOUCHED_MAX_BYTES = 1024 * 1024;

  if (
    typeof window.createImageBitmap !== 'function' ||
    typeof window.HTMLCanvasElement !== 'function' ||
    typeof HTMLCanvasElement.prototype.toBlob !== 'function' ||
    typeof window.DataTransfer !== 'function'
  ) {
    return;
  }

  function jpegName(name) {
    var stem = (name || '').replace(/\.[^.]*$/, '');
    return (stem || 'photo') + '.jpg';
  }

  function canvasToBlob(canvas) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(
        function (blob) {
          if (blob) {
            resolve(blob);
          } else {
            reject(new Error('Canvas export failed'));
          }
        },
        'image/jpeg',
        JPEG_QUALITY
      );
    });
  }

  // Resolves to a smaller JPEG File, or to null when the original should stay.
  function shrink(file) {
    return createImageBitmap(file, { imageOrientation: 'from-image' }).then(function (bitmap) {
      var longEdge = Math.max(bitmap.width, bitmap.height);
      if (longEdge <= MAX_EDGE_PX && file.size <= UNTOUCHED_MAX_BYTES) {
        bitmap.close();
        return null;
      }

      var scale = Math.min(1, MAX_EDGE_PX / longEdge);
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      var context = canvas.getContext('2d');
      // JPEG has no transparency; white matches what the server composites onto.
      context.fillStyle = '#fff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.imageSmoothingQuality = 'high';
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();

      return canvasToBlob(canvas).then(function (blob) {
        // Re-encoding an already-compact photo can make it bigger.
        if (blob.size >= file.size) {
          return null;
        }
        return new File([blob], jpegName(file.name), {
          type: 'image/jpeg',
          lastModified: file.lastModified,
        });
      });
    });
  }

  function enhance(input) {
    var form = input.form;
    if (!form) {
      return;
    }
    var status = form.querySelector('[data-shrink-status]');
    var submits = form.querySelectorAll('button[type="submit"], input[type="submit"]');
    // Each selection gets a number; a result is applied only if no newer
    // selection has been made since, so a slow earlier photo cannot win.
    var latest = 0;
    var busy = false;

    function setBusy(value) {
      busy = value;
      for (var i = 0; i < submits.length; i++) {
        submits[i].disabled = value;
      }
      if (status) {
        status.textContent = value ? 'Preparing photo…' : '';
      }
    }

    // Disabled buttons already stop clicks and Enter; this also covers
    // form.requestSubmit() and anything else that bypasses them.
    form.addEventListener('submit', function (event) {
      if (busy) {
        event.preventDefault();
      }
    });

    input.addEventListener('change', function () {
      var job = ++latest;
      var file = input.files && input.files[0];
      if (!file) {
        setBusy(false);
        return;
      }

      setBusy(true);
      // Promise.resolve().then() so a synchronous throw lands in catch() too.
      Promise.resolve()
        .then(function () {
          return shrink(file);
        })
        .then(function (smaller) {
          if (smaller && job === latest) {
            var transfer = new DataTransfer();
            transfer.items.add(smaller);
            // Assigning files fires no change event, so this does not loop.
            input.files = transfer.files;
          }
        })
        .catch(function () {
          // Leave the original selected; the server normalizes it.
        })
        .then(function () {
          if (job === latest) {
            setBusy(false);
          }
        });
    });
  }

  var inputs = document.querySelectorAll('input[type="file"][data-shrink-photo]');
  for (var i = 0; i < inputs.length; i++) {
    enhance(inputs[i]);
  }
})();
