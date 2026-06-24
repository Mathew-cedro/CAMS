// 1. The Bouncer (Security Check)
document.addEventListener('DOMContentLoaded', () => {
    const role = localStorage.getItem('cams_role');
    if (role !== 'Admin') window.location.href = 'login.html';
});

// 2. Tab Switcher
function switchTab(target) {
    document.querySelectorAll('.view-section').forEach(sec => sec.style.display = 'none');
    document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
    document.getElementById('view-' + target).style.display = 'block';
    document.getElementById('nav-' + target).classList.add('active');
    document.getElementById('page-title').innerText = target === 'dashboard' ? 'Municipal Dashboard' : 'Beneficiary Registry';
}

// 3. AI Fetch
async function generateAIReport() {
    const aiOutput = document.getElementById('ai-text');
    aiOutput.innerText = "Analyzing local database metrics...";
    try {
        const res = await fetch('http://127.0.0.1:8000/api/reports/ai-summary');
        const data = await res.json();
        aiOutput.innerText = data.status === "success" ? `"${data.summary}"` : "Error: " + data.message;
    } catch (err) {
        aiOutput.innerText = "Connection to FastAPI failed. Is the server running?";
    }
}

// 4. Logout
function logout() {
    localStorage.removeItem('cams_role');
    window.location.href = 'login.html';
}

let currentModalType = ''; // Tracks if we are adding a program or beneficiary

function openModal(type) {
    currentModalType = type;
    document.getElementById('dynamic-modal').style.display = 'flex';
    
    if (type === 'program') {
        document.getElementById('modal-title').innerText = "Create New Assistance Program";
        document.getElementById('form-program').style.display = 'block';
    }
}

function closeModal() {
    document.getElementById('dynamic-modal').style.display = 'none';
    document.getElementById('form-program').style.display = 'none';
    
    // Clear inputs
    document.getElementById('prog-name').value = '';
    document.getElementById('prog-budget').value = '';
}

function saveDynamicEntry() {
    if (currentModalType === 'program') {
        const name = document.getElementById('prog-name').value;
        const budget = document.getElementById('prog-budget').value;
        
        if(name === '') return alert("Please enter a program name.");

        // Create a new row in the HTML table instantly
        const table = document.getElementById('table-progs');
        const newRow = table.insertRow();
        newRow.innerHTML = `
            <td>${name}</td>
            <td>₱ ${Number(budget).toLocaleString()}</td>
            <td>0</td>
            <td><button style="color:red; cursor:pointer; background:none; border:none; font-weight:bold;">Close</button></td>
        `;
        
        // TODO later: Add a fetch() here to send this data to Python SQLite!
    }
    
    closeModal();
}