document.addEventListener('DOMContentLoaded', function () {

    const grid = GridStack.init({
        float: true,
        cellHeight: 100,
        disableResize: false,
        disableDrag: false
    });

    document.querySelectorAll('.grid-stack-item')
        .forEach(loadWidget);

});


function loadWidget(element) {

    const widgetId = element.dataset.widgetId;

    fetch(`/analytics/api/widget/${widgetId}/`)
        .then(response => response.json())
        .then(data => {

            const canvas = document.getElementById(
                `chart-${widgetId}`
            );

            new Chart(canvas, {

                type: data.chart_type,

                data: {

                    labels: data.labels,

                    datasets: [{

                        label: data.title,

                        data: data.values

                    }]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false
                }
            });

        });

}