// Sample event data
const eventData = [
    {
        id: 1,
        title: 'Tech Conference 2026',
        category: 'conference',
        location: 'San Francisco, USA',
        country: 'United States',
        latitude: 37.7749,
        longitude: -122.4194,
        date: '2026-04-20',
        description: 'Annual technology summit bringing together innovators and industry leaders to discuss the future of AI and software development.'
    },
    {
        id: 2,
        title: 'Mount Fuji Earthquake',
        category: 'disaster',
        location: 'Mount Fuji, Japan',
        country: 'Japan',
        latitude: 35.3607,
        longitude: 138.7274,
        date: '2026-04-15',
        description: 'Moderate earthquake detected near Mount Fuji region. Authorities monitoring volcanic activity closely.'
    },
    {
        id: 3,
        title: 'London Music Festival',
        category: 'festival',
        location: 'London, UK',
        country: 'United Kingdom',
        latitude: 51.5074,
        longitude: -0.1278,
        date: '2026-05-01',
        description: 'Annual music festival featuring international artists and emerging talent from around the world.'
    },
    {
        id: 4,
        title: 'Climate Action Rally',
        category: 'protest',
        location: 'Berlin, Germany',
        country: 'Germany',
        latitude: 52.5200,
        longitude: 13.4050,
        date: '2026-04-22',
        description: 'Large-scale protest demanding stronger climate policies and environmental protection measures.'
    },
    {
        id: 5,
        title: 'Sydney Food Expo',
        category: 'festival',
        location: 'Sydney, Australia',
        country: 'Australia',
        latitude: -33.8688,
        longitude: 151.2093,
        date: '2026-04-25',
        description: 'Culinary showcase featuring chefs and food producers from across the Asia-Pacific region.'
    },
    {
        id: 6,
        title: 'Amazon Flooding Crisis',
        category: 'disaster',
        location: 'Amazon Basin, Brazil',
        country: 'Brazil',
        latitude: -3.4653,
        longitude: -62.2159,
        date: '2026-04-10',
        description: 'Severe flooding affecting multiple communities in the Amazon region. Humanitarian aid being coordinated.'
    },
    {
        id: 7,
        title: 'Dubai Innovation Summit',
        category: 'conference',
        location: 'Dubai, UAE',
        country: 'United Arab Emirates',
        latitude: 25.2048,
        longitude: 55.2708,
        date: '2026-05-05',
        description: 'International conference showcasing cutting-edge innovations in renewable energy and smart city technologies.'
    },
    {
        id: 8,
        title: 'Singapore Marathon',
        category: 'festival',
        location: 'Singapore',
        country: 'Singapore',
        latitude: 1.3521,
        longitude: 103.8198,
        date: '2026-04-28',
        description: 'Annual marathon event with over 50,000 participants from around the world.'
    },
    {
        id: 9,
        title: 'Volcanic Eruption Warning',
        category: 'disaster',
        location: 'Mount Merapi, Indonesia',
        country: 'Indonesia',
        latitude: -7.5407,
        longitude: 110.4430,
        date: '2026-04-14',
        description: 'Indonesian volcano shows increased activity. Local communities advised to prepare evacuation plans.'
    },
    {
        id: 10,
        title: 'Paris Fashion Week',
        category: 'festival',
        location: 'Paris, France',
        country: 'France',
        latitude: 48.8566,
        longitude: 2.3522,
        date: '2026-05-10',
        description: 'Premier fashion showcase featuring designs from top houses and emerging designers worldwide.'
    }
];

const categoryColors = {
    disaster: '#ff4444',
    conference: '#4488ff',
    protest: '#ffcc00',
    festival: '#44ff44'
};

// Canvas setup
let canvas, ctx;
let rotation = 0;
let isDragging = false;
let dragStartX = 0;
let selectedEvent = null;

function init() {
    canvas = document.getElementById('globeCanvas');
    ctx = canvas.getContext('2d');

    // Set canvas size
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Mouse events
    canvas.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('click', onCanvasClick);
    canvas.addEventListener('wheel', onMouseWheel);

    // Sidebar events
    document.getElementById('eventSearch').addEventListener('input', filterEvents);
    document.querySelectorAll('.category-filter').forEach(checkbox => {
        checkbox.addEventListener('change', filterEvents);
    });

    // Control buttons
    document.getElementById('resetView').addEventListener('click', resetView);
    document.getElementById('toggleLabels').addEventListener('click', toggleLabels);

    // Populate events list
    updateEventsList(eventData);

    // Start animation loop
    animate();
}

function resizeCanvas() {
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
}

function latLonToPixel(lat, lon) {
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) / 2 - 20;

    const phi = (90 - lat) * Math.PI / 180;
    const theta = (lon + rotation) * Math.PI / 180;

    const x = centerX + radius * Math.sin(phi) * Math.cos(theta);
    const y = centerY - radius * Math.cos(phi);

    return { x, y };
}

function drawGlobe() {
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) / 2 - 20;

    // Clear canvas
    ctx.fillStyle = '#f0f8ff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw globe circle
    ctx.strokeStyle = '#4488ff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // Draw latitude lines
    ctx.strokeStyle = 'rgba(68, 136, 255, 0.3)';
    ctx.lineWidth = 1;
    for (let lat = -60; lat <= 60; lat += 30) {
        const points = [];
        for (let lon = -180; lon <= 180; lon += 5) {
            points.push(latLonToPixel(lat, lon));
        }

        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();
    }

    // Draw longitude lines
    for (let lon = -180; lon <= 180; lon += 30) {
        const points = [];
        for (let lat = -90; lat <= 90; lat += 5) {
            points.push(latLonToPixel(lat, lon));
        }

        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();
    }

    // Draw equator and prime meridian
    ctx.strokeStyle = 'rgba(68, 136, 255, 0.6)';
    ctx.lineWidth = 2;

    // Equator
    const equatorPoints = [];
    for (let lon = -180; lon <= 180; lon += 5) {
        equatorPoints.push(latLonToPixel(0, lon));
    }
    ctx.beginPath();
    ctx.moveTo(equatorPoints[0].x, equatorPoints[0].y);
    for (let i = 1; i < equatorPoints.length; i++) {
        ctx.lineTo(equatorPoints[i].x, equatorPoints[i].y);
    }
    ctx.stroke();

    // Prime meridian
    const meridianPoints = [];
    for (let lat = -90; lat <= 90; lat += 5) {
        meridianPoints.push(latLonToPixel(lat, 0));
    }
    ctx.beginPath();
    ctx.moveTo(meridianPoints[0].x, meridianPoints[0].y);
    for (let i = 1; i < meridianPoints.length; i++) {
        ctx.lineTo(meridianPoints[i].x, meridianPoints[i].y);
    }
    ctx.stroke();

    // Draw event pins
    drawEventPins();
}

function drawEventPins() {
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) / 2 - 20;

    eventData.forEach(event => {
        const pos = latLonToPixel(event.latitude, event.longitude);

        // Check if point is visible (on front of globe)
        const phi = (90 - event.latitude) * Math.PI / 180;
        const theta = (event.longitude + rotation) * Math.PI / 180;
        const z = Math.cos(phi) * Math.cos(theta);

        if (z > -0.3) { // Only draw points facing camera
            const color = categoryColors[event.category] || '#ff00ff';

            // Draw glow
            ctx.fillStyle = color.replace(')', ', 0.2)').replace('rgb', 'rgba');
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, 12, 0, Math.PI * 2);
            ctx.fill();

            // Draw pin
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, 6, 0, Math.PI * 2);
            ctx.fill();

            // Draw border
            ctx.strokeStyle = 'white';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Check if mouse is over this pin
            if (isMouseOverPin(pos)) {
                ctx.lineWidth = 3;
                ctx.strokeStyle = color;
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 10, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
    });
}

let mouseX = 0;
let mouseY = 0;

function onMouseDown(e) {
    isDragging = true;
    dragStartX = e.clientX;
}

function onMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;

    if (isDragging) {
        const deltaX = e.clientX - dragStartX;
        rotation -= deltaX * 0.5;
        dragStartX = e.clientX;
    }

    // Show tooltip
    const hoveredEvent = getEventAtMouse();
    const tooltip = document.getElementById('tooltip');
    if (hoveredEvent) {
        tooltip.textContent = hoveredEvent.title;
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 10) + 'px';
        tooltip.style.top = (e.clientY + 10) + 'px';
        canvas.style.cursor = 'pointer';
    } else {
        tooltip.style.display = 'none';
        canvas.style.cursor = 'default';
    }
}

function onMouseUp() {
    isDragging = false;
}

function onCanvasClick() {
    const event = getEventAtMouse();
    if (event) {
        showEventDetails(event);
        selectedEvent = event;
        updateEventsList(eventData);
    }
}

function onMouseWheel(e) {
    e.preventDefault();
    // Could add zoom in future
}

function isMouseOverPin(pinPos) {
    const dist = Math.sqrt(
        Math.pow(mouseX - pinPos.x, 2) +
        Math.pow(mouseY - pinPos.y, 2)
    );
    return dist < 12;
}

function getEventAtMouse() {
    for (let event of eventData) {
        const phi = (90 - event.latitude) * Math.PI / 180;
        const theta = (event.longitude + rotation) * Math.PI / 180;
        const z = Math.cos(phi) * Math.cos(theta);

        if (z > -0.3) {
            const pos = latLonToPixel(event.latitude, event.longitude);
            if (isMouseOverPin(pos)) {
                return event;
            }
        }
    }
    return null;
}

function showEventDetails(event) {
    const panel = document.getElementById('eventDetails');
    const emptyState = document.getElementById('emptyState');

    document.getElementById('eventTitle').textContent = event.title;
    document.getElementById('eventCategory').textContent = event.category.toUpperCase();
    document.getElementById('eventCategory').style.background = categoryColors[event.category];
    document.getElementById('eventDate').textContent = formatDate(event.date);
    document.getElementById('eventDescription').textContent = event.description;
    document.getElementById('eventLocation').innerHTML =
        `<strong>Location:</strong> ${event.location}<br><strong>Country:</strong> ${event.country}`;

    panel.style.display = 'block';
    emptyState.style.display = 'none';
}

function closeEventDetails() {
    document.getElementById('eventDetails').style.display = 'none';
    document.getElementById('emptyState').style.display = 'block';
    selectedEvent = null;
    updateEventsList(eventData);
}

function updateEventsList(events) {
    const list = document.getElementById('eventsList');
    list.innerHTML = '';

    events.forEach(event => {
        const eventEl = document.createElement('div');
        eventEl.className = 'event-item' + (selectedEvent?.id === event.id ? ' active' : '');
        eventEl.innerHTML = `
            <div class="event-item-title">${event.title}</div>
            <div class="event-item-location">${event.country}</div>
            <span class="event-item-category">${event.category}</span>
        `;
        eventEl.addEventListener('click', () => {
            showEventDetails(event);
            selectedEvent = event;
            updateEventsList(events);
        });
        list.appendChild(eventEl);
    });
}

function filterEvents() {
    const searchTerm = document.getElementById('eventSearch').value.toLowerCase();
    const selectedCategories = Array.from(document.querySelectorAll('.category-filter:checked'))
        .map(el => el.value);

    const filtered = eventData.filter(event => {
        const matchesSearch = event.title.toLowerCase().includes(searchTerm) ||
            event.location.toLowerCase().includes(searchTerm) ||
            event.country.toLowerCase().includes(searchTerm);

        const matchesCategory = selectedCategories.length === 0 ||
            selectedCategories.includes(event.category);

        return matchesSearch && matchesCategory;
    });

    updateEventsList(filtered);
}

function resetView() {
    rotation = 0;
}

function toggleLabels() {
    // Can be implemented for showing/hiding labels
}

function formatDate(dateString) {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

function animate() {
    drawGlobe();
    requestAnimationFrame(animate);
}

// Initialize when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
