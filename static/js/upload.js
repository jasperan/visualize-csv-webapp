(() => {
    const dropZone = document.getElementById('drop-zone');
    const input = document.getElementById('file-input');
    const sample = document.getElementById('sample-btn');
    const progressBar = document.getElementById('progress-bar');
    let busy = false;

    function showState(state) {
        busy = state === 'progress';
        ['idle', 'progress', 'error'].forEach(name => document.getElementById('upload-' + name).classList.toggle('hidden', state !== name));
        dropZone.setAttribute('aria-busy', busy);
        sample.disabled = busy;
        input.disabled = busy;
    }
    function fail(message) {
        document.getElementById('error-message').textContent = message;
        showState('error');
    }
    function browse(event) {
        event.stopPropagation();
        if (!busy) { input.value = ''; input.click(); }
    }
    document.getElementById('browse-btn').addEventListener('click', browse);
    document.getElementById('retry-btn').addEventListener('click', browse);
    dropZone.addEventListener('dragover', event => { event.preventDefault(); if (!busy) dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', event => {
        event.preventDefault();
        dropZone.classList.remove('drag-over');
        if (!busy && event.dataTransfer.files.length) uploadFile(event.dataTransfer.files[0]);
    });
    input.addEventListener('change', () => { if (input.files.length) uploadFile(input.files[0]); });
    sample.addEventListener('click', async () => {
        if (busy) return;
        showState('progress');
        document.getElementById('upload-filename').textContent = 'Loading sample dataset…';
        try {
            const response = await fetch('/static/sample.csv');
            if (!response.ok) throw new Error('The sample could not be loaded. Please try again.');
            uploadFile(new File([await response.blob()], 'studio-revenue.csv', { type: 'text/csv' }));
        } catch (error) { fail(error.message); }
    });

    function uploadFile(file) {
        if (!/\.(csv|tsv)$/i.test(file.name)) return fail('Choose a .csv or .tsv file to continue.');
        if (file.size > 100 * 1024 * 1024) return fail('This file is larger than 100 MB. Try a smaller file.');
        showState('progress');
        document.getElementById('upload-filename').textContent = file.name;
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', '0');
        const form = new FormData();
        form.append('file', file);
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload');
        xhr.timeout = 120000;
        xhr.upload.onprogress = event => {
            if (!event.lengthComputable) return;
            const percent = Math.round(event.loaded / event.total * 100);
            progressBar.style.width = percent + '%';
            progressBar.setAttribute('aria-valuenow', percent);
        };
        xhr.onload = () => {
            let response;
            try { response = JSON.parse(xhr.responseText); }
            catch { return fail('The server could not read this file. Please try again.'); }
            if (xhr.status === 200 && response.redirect) window.location.href = response.redirect;
            else fail(response.error || 'Upload failed. Please try again.');
        };
        xhr.onerror = () => fail('Connection interrupted. Check your connection and try again.');
        xhr.ontimeout = () => fail('Upload timed out. Try a smaller file or check your connection.');
        xhr.send(form);
    }
})();
