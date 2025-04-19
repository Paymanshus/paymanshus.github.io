// Theme toggle functionality
const themeToggle = document.getElementById('themeToggle');
const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');

// Function to set theme
function setTheme(isDark) {
    document.body.classList.toggle('dark-theme', isDark);
    const icon = themeToggle.querySelector('i');
    icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

// Initialize theme based on localStorage or system preference
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        setTheme(savedTheme === 'dark');
    } else {
        setTheme(prefersDarkScheme.matches);
    }
}

// Toggle theme on button click
themeToggle.addEventListener('click', () => {
    const isDark = document.body.classList.contains('dark-theme');
    setTheme(!isDark);
});

// Listen for system theme changes
prefersDarkScheme.addEventListener('change', (e) => {
    if (!localStorage.getItem('theme')) {
        setTheme(e.matches);
    }
});

// Initialize theme when page loads
initializeTheme();