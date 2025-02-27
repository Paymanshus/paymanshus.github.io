// Custom cursor - Commented out as requested but kept for future reference
/*
const cursor = document.querySelector('.cursor');
const cursorFollower = document.querySelector('.cursor-follower');
const links = document.querySelectorAll('a');

document.addEventListener('mousemove', (e) => {
    cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px';

    setTimeout(() => {
        cursorFollower.style.left = e.clientX + 'px';
        cursorFollower.style.top = e.clientY + 'px';
    }, 100);
});

document.addEventListener('mousedown', () => {
    cursor.style.transform = 'translate(-50%, -50%) scale(0.7)';
    cursorFollower.style.transform = 'translate(-50%, -50%) scale(0.7)';
});

document.addEventListener('mouseup', () => {
    cursor.style.transform = 'translate(-50%, -50%) scale(1)';
    cursorFollower.style.transform = 'translate(-50%, -50%) scale(1)';
});

links.forEach(link => {
    link.addEventListener('mouseenter', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1.5)';
        cursor.style.backgroundColor = 'transparent';
        cursor.style.border = '2px solid var(--secondary-color)';
        cursorFollower.style.opacity = '0.3';
    });

    link.addEventListener('mouseleave', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1)';
        cursor.style.backgroundColor = 'var(--secondary-color)';
        cursor.style.border = 'none';
        cursorFollower.style.opacity = '0.5';
    });
});
*/

// Countdown timer - Commented out as requested but kept for future reference
/*
const countdownDate = new Date();
countdownDate.setDate(countdownDate.getDate() + 30); // 30 days from now

function updateCountdown() {
    const now = new Date().getTime();
    const distance = countdownDate - now;

    // Time calculations
    const days = Math.floor(distance / (1000 * 60 * 60 * 24));
    const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((distance % (1000 * 60)) / 1000);

    // Display results
    document.querySelector('.days').textContent = days < 10 ? `0${days}` : days;
    document.querySelector('.hours').textContent = hours < 10 ? `0${hours}` : hours;
    document.querySelector('.minutes').textContent = minutes < 10 ? `0${minutes}` : minutes;
    document.querySelector('.seconds').textContent = seconds < 10 ? `0${seconds}` : seconds;

    // If countdown is finished
    if (distance < 0) {
        clearInterval(countdownTimer);
        document.querySelector('.countdown').innerHTML = "<h3>Blog is now live!</h3>";
    }
}

// Update countdown every second
const countdownTimer = setInterval(updateCountdown, 1000);
updateCountdown(); // Initial call
*/

// Notification button
const notifyBtn = document.querySelector('.notify-btn');
if (notifyBtn) {
    notifyBtn.addEventListener('click', () => {
        alert('Thank you! You will be notified when the blog launches.');
        notifyBtn.textContent = 'You will be notified!';
        notifyBtn.disabled = true;
    });
}

// Smooth scrolling for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();

        const targetId = this.getAttribute('href');
        if (targetId === '#') return;

        const targetElement = document.querySelector(targetId);
        if (targetElement) {
            window.scrollTo({
                top: targetElement.offsetTop,
                behavior: 'smooth'
            });
        }
    });
});

// Animate elements on scroll
const animateOnScroll = () => {
    const elements = document.querySelectorAll('.animate-on-scroll');

    elements.forEach(element => {
        const elementPosition = element.getBoundingClientRect().top;
        const windowHeight = window.innerHeight;

        if (elementPosition < windowHeight - 100) {
            element.classList.add('animated');
        }
    });
};

window.addEventListener('scroll', animateOnScroll);
animateOnScroll(); // Initial check