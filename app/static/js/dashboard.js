document.addEventListener("DOMContentLoaded", () => {



    const page = document.querySelector("[data-dashboard-page]");



    if (!page) {

        return;

    }



    document.body.classList.add("dashboard-screen");



    const dashboardUrl = page.dataset.dashboardUrl;

    const initialJson = page.querySelector("[data-dashboard-initial-json]");



    let dashboard = JSON.parse(initialJson?.textContent || "{}");



    const filterButton = page.querySelector("[data-dashboard-filter-button]");

    const filterLabel = page.querySelector("[data-dashboard-filter-label]");

    const filterMenu = page.querySelector("[data-dashboard-filter-menu]");

    const fromInput = page.querySelector("[data-dashboard-from]");

    const toInput = page.querySelector("[data-dashboard-to]");

    const customApply = page.querySelector("[data-dashboard-custom-apply]");

    const chart = page.querySelector("[data-dashboard-chart]");

    const chartWrap = page.querySelector("[data-dashboard-chart-wrap]");

    const chartTooltip = page.querySelector("[data-chart-tooltip]");

    const trendMetricButtons = [
        ...page.querySelectorAll(
            "[data-trend-metric]"
        )
    ];

    let trendMetric = "bad";



    const SVG_NS = "http://www.w3.org/2000/svg";






    /* =====================================================

       FORMATTERS

       ===================================================== */



    const integerFormat = new Intl.NumberFormat("en-US", {

        maximumFractionDigits: 0,

    });



    const num = (value) => Number(value || 0);



    const oneDecimal = (value) => num(value).toFixed(1);



    /* 42.0 -> "42%", 79.6 -> "79.6%" */

    const trimPercent = (value) =>

        `${num(value).toFixed(1).replace(/\.0$/, "")}%`;



    /* -38.0 -> "-38%", 5.4 -> "+5.4%" */

    const signedTrimPercent = (value) => {

        const number = num(value);

        return `${number >= 0 ? "+" : ""}${trimPercent(number)}`;

    };



    const formatUptime = (value) => {

        if (value === null || value === undefined || value === "") {

            return "—";

        }

        if (typeof value === "string") {

            return value;

        }

        const seconds = Math.max(0, Number(value));

        const hours = Math.floor(seconds / 3600);

        const minutes = Math.floor((seconds % 3600) / 60);

        return `${hours}h ${minutes}m`;

    };



    const formatCompact = (value) => {

        if (value === null || value === undefined || value === "") {

            return "—";

        }

        if (typeof value === "string") {

            return value;

        }

        const number = Number(value);

        if (number >= 1e6) {

            return `${(number / 1e6).toFixed(2).replace(/\.?0+$/, "")}M`;

        }

        if (number >= 1e3) {

            return `${(number / 1e3).toFixed(1).replace(/\.0$/, "")}K`;

        }

        return integerFormat.format(number);

    };



    const formatFps = (value) => {

        if (value === null || value === undefined || value === "") {

            return "—";

        }

        if (typeof value === "string") {

            return value;

        }

        return `${Math.round(Number(value))} FPS`;

    };



    const cssVar = (name, fallback) =>

        getComputedStyle(page).getPropertyValue(name).trim() || fallback;





    /* =====================================================

       DOM HELPERS

       ===================================================== */



    const setText = (selector, value) => {

        const element = page.querySelector(selector);

        if (element) {

            element.textContent = value;

        }

    };



    const setGapClass = (selector, value, negativeWhenPositive = false) => {

        const element = page.querySelector(selector);

        if (!element) {

            return;

        }

        element.classList.remove("is-negative", "is-positive");

        const negative = negativeWhenPositive

            ? Number(value) > 0

            : Number(value) < 0;

        element.classList.add(negative ? "is-negative" : "is-positive");

    };





    /* =====================================================

       RENDER

       ===================================================== */



    function renderDashboard(data) {



        dashboard = data;



        const kpi = data.kpi || {};

        const targets = data.targets || {};

        const processing = data.processing || {};

        const cumulative = data.cumulative || {};

        const camera = data.camera || {};



        const gap = num(kpi.yield_gap);

        const yieldTarget = num(targets.yield_percent);





        /* Summary strip */



        setText("[data-summary-batches]", integerFormat.format(num(kpi.total_batches)));

        setText("[data-summary-products]", integerFormat.format(num(kpi.total_products)));

        setText("[data-summary-yield]", `${oneDecimal(kpi.yield_percent)}%`);

        setText("[data-summary-gap]", `${Math.abs(gap).toFixed(1)}%`);

        setText("[data-summary-direction]", gap >= 0 ? "above" : "below");

        setText("[data-summary-target]", `${Math.round(yieldTarget)}%`);





        /* Yield card */



        setText("[data-kpi-yield]", `${oneDecimal(kpi.yield_percent)}%`);

        setText("[data-target-yield]", `${yieldTarget.toFixed(1)}%`);

        setText("[data-yield-gap-direction]", gap >= 0 ? "above by" : "below by");

        setText("[data-kpi-yield-gap]", `${Math.abs(gap).toFixed(1)}%`);

        setGapClass("[data-kpi-yield-gap]", gap);



        /* Day-over-day change. Uses kpi.yield_delta from the backend if

           present; otherwise derives it from the last two trend days

           (yield = 100 − bad ratio). */

        const delta = page.querySelector("[data-yield-delta]");

        const trend = data.trend || [];

        let deltaValue = kpi.yield_delta;

        let deltaTitle = "";



        if ((deltaValue === null || deltaValue === undefined || deltaValue === "")

            && trend.length >= 2) {

            const today = trend[trend.length - 1];

            const yesterday = trend[trend.length - 2];

            deltaValue = num(yesterday.defect_percent) - num(today.defect_percent);

            deltaTitle = `${today.label} vs ${yesterday.label}`;

        }



        if (delta) {

            if (deltaValue === null || deltaValue === undefined || deltaValue === "") {

                delta.hidden = true;

            } else {

                const deltaNumber = Number(deltaValue);

                delta.hidden = false;

                delta.title = deltaTitle;

                delta.classList.toggle("is-down", deltaNumber < 0);

                setText("[data-yield-delta-arrow]", deltaNumber < 0 ? "▼" : "▲");

                setText("[data-yield-delta-value]", `${Math.abs(deltaNumber).toFixed(1)}%`);

            }

        }



        const yieldFill = page.querySelector("[data-yield-progress]");

        if (yieldFill) {

            yieldFill.style.width =

                `${Math.min(100, Math.max(0, num(kpi.yield_percent)))}%`;

        }



        const targetMarker = page.querySelector("[data-yield-target-marker]");

        if (targetMarker) {

            targetMarker.style.left = `${Math.min(100, Math.max(0, yieldTarget))}%`;

        }



        const targetLabel = page.querySelector("[data-progress-target-label]");

        if (targetLabel) {

            targetLabel.textContent = `${Math.round(yieldTarget)}% (target)`;

            targetLabel.style.left = `${Math.min(88, Math.max(12, yieldTarget))}%`;

        }





        /* Composition */



        setText("[data-kpi-total-products]", integerFormat.format(num(kpi.total_products)));



        (data.composition || []).forEach((item) => {



            const segment = page.querySelector(`[data-composition-segment="${item.key}"]`);

            if (segment) {

                segment.style.width = `${num(item.percent)}%`;

                segment.style.background = item.colour;

            }



            const dot = page.querySelector(`[data-composition-dot="${item.key}"]`);

            if (dot) {

                dot.style.background = item.colour;

            }



            setText(`[data-composition-count="${item.key}"]`, integerFormat.format(num(item.count)));

            setText(`[data-composition-percent="${item.key}"]`, `${oneDecimal(item.percent)}%`);

        });





        /* Overall vs Target */



        setText("[data-target-row-yield-overall]", trimPercent(kpi.yield_percent));

        setText("[data-target-row-yield-target]", trimPercent(targets.yield_percent));

        setText("[data-target-row-yield-gap]", signedTrimPercent(kpi.yield_gap));

        setGapClass("[data-target-row-yield-gap]", kpi.yield_gap);



        setText("[data-target-row-defect-overall]", trimPercent(kpi.defect_percent));

        setText("[data-target-row-defect-target]", trimPercent(targets.defect_percent));

        setText("[data-target-row-defect-gap]", signedTrimPercent(kpi.defect_gap));

        setGapClass("[data-target-row-defect-gap]", kpi.defect_gap, true);



        setText("[data-target-row-pass-overall]", trimPercent(kpi.batch_pass_percent));

        setText("[data-target-row-pass-target]", trimPercent(targets.batch_pass_percent));

        setText("[data-target-row-pass-gap]", signedTrimPercent(kpi.batch_pass_gap));

        setGapClass("[data-target-row-pass-gap]", kpi.batch_pass_gap);





        /* Camera & Runtime */



        setText("[data-camera-uptime]", formatUptime(camera.uptime_seconds ?? camera.uptime));

        setText("[data-camera-frames]", formatCompact(camera.frames_processed));

        setText("[data-camera-fps]", formatFps(camera.average_fps));





        /* Cumulative */



        setText("[data-cumulative-batches]", integerFormat.format(num(kpi.total_batches)));

        setText("[data-cumulative-products]", integerFormat.format(num(kpi.total_products)));

        setText("[data-cumulative-average]",

            integerFormat.format(Math.round(num(cumulative.average_products_per_batch))));

        setText("[data-cumulative-detection-confidence]",

            num(cumulative.average_detection_confidence ?? processing.average_class_confidence).toFixed(2));





        /* Filter */



        if (filterLabel && data.filter) {

            filterLabel.textContent =

                `${data.filter.label} · ${num(kpi.total_batches)} inspections`;

        }



        if (fromInput) {

            fromInput.value = data.filter?.from || "";

        }



        if (toInput) {

            toInput.value = data.filter?.to || "";

        }



        page.querySelectorAll("[data-dashboard-range]").forEach((button) => {

            button.classList.toggle(

                "is-active",

                button.dataset.dashboardRange === data.filter?.range

            );

        });



        drawChart();

    }





    /* =====================================================

       SVG HELPERS

       ===================================================== */



    function svg(name, attributes = {}) {

        const element = document.createElementNS(SVG_NS, name);

        Object.entries(attributes).forEach(([key, value]) => {

            element.setAttribute(key, String(value));

        });

        return element;

    }



    function addText(parent, text, attributes = {}, className = "") {

        const element = svg("text", attributes);

        if (className) {

            element.setAttribute("class", className);

        }

        element.textContent = text;

        parent.appendChild(element);

        return element;

    }



    function niceAxis(rawMinimum, rawMaximum) {

        const padding = Math.max(4, (rawMaximum - rawMinimum) * 0.4);

        const low = rawMinimum - padding;

        const high = rawMaximum + padding;

        const steps = [1, 2, 5, 10, 20, 25];



        for (const step of steps) {

            const minimum = Math.max(0, Math.floor(low / step) * step);

            const maximum = Math.min(100, Math.ceil(high / step) * step);

            if ((maximum - minimum) / step <= 10) {

                return { minimum, maximum, step };

            }

        }



        return { minimum: 0, maximum: 100, step: 10 };

    }





    /* =====================================================

       QUALITY TREND CHART

       Drawn in real pixels (viewBox = container size), so

       spacing matches the reference at any window size.

       ===================================================== */



    function drawChart() {



        if (!chart) {

            return;

        }



        const width = Math.max(320, Math.round(chartWrap?.clientWidth || 890));

        const height = Math.max(220, Math.round(chartWrap?.clientHeight || 335));



        chart.setAttribute("viewBox", `0 0 ${width} ${height}`);

        chart.replaceChildren();



        if (chartTooltip) {

            chartTooltip.hidden = true;

        }



        const brand = cssVar("--dash-brand", "#741F2E");

        const green =
            cssVar(
                "--dash-green",
                "#7FA06F"
            );

        const isGoodRatio =
            trendMetric === "good";

        const metricLabel =
            isGoodRatio
                ? "Good Ratio"
                : "Bad Ratio";

        const seriesColour =
            isGoodRatio
                ? green
                : brand;

        const points = dashboard.trend || [];



        const plot = {

            left: 58,

            right: width - 23,

            top: 34,

            bottom: height - 48,

        };



        const pointsLeft = plot.left + 43;

        const pointsRight = plot.right - 25;





        if (!points.length) {

            addText(chart, "No trend data for this period", {

                x: width / 2,

                y: height / 2,

                "text-anchor": "middle",

                "font-size": 13,

            });

            return;

        }





        const target =
            isGoodRatio
                ? num(
                    dashboard.targets?.yield_percent
                )
                : num(
                    dashboard.targets?.defect_percent
                );

        const metricValue = (point) => {

            const defect =
                num(
                    point?.defect_percent
                );

            return isGoodRatio
                ? Math.max(
                    0,
                    Math.min(
                        100,
                        100 - defect
                    )
                )
                : defect;

        };

        const values =
            points.map(
                metricValue
            );

        chart.style.setProperty(
            "--dashboard-trend-colour",
            seriesColour
        );

        chart.setAttribute(
            "aria-label",
            `Daily ${metricLabel.toLowerCase()} quality trend`
        );



        const axis = niceAxis(

            Math.min(...values, target),

            Math.max(...values, target)

        );



        const span = Math.max(1, axis.maximum - axis.minimum);



        /* Header stats: average / best / worst day */



        const average = values.reduce((sum, value) => sum + value, 0) / values.length;

        const bestIndex =
            isGoodRatio
                ? values.indexOf(
                    Math.max(...values)
                )
                : values.indexOf(
                    Math.min(...values)
                );

        const worstIndex =
            isGoodRatio
                ? values.indexOf(
                    Math.min(...values)
                )
                : values.indexOf(
                    Math.max(...values)
                );



        setText("[data-trend-average]", `${average.toFixed(1)}%`);

        setText("[data-trend-best]",

            `${values[bestIndex].toFixed(1)}% · ${points[bestIndex].label}`);

        setText("[data-trend-worst]",

            `${values[worstIndex].toFixed(1)}% · ${points[worstIndex].label}`);



        const xForIndex = (index) =>

            points.length === 1

                ? (pointsLeft + pointsRight) / 2

                : pointsLeft + (index / (points.length - 1)) * (pointsRight - pointsLeft);



        const yForValue = (value) =>

            plot.top + (1 - (value - axis.minimum) / span) * (plot.bottom - plot.top);





        /* Background: tinted "above target" zone + soft grid */



        const targetY = yForValue(target);

        const gridColour = cssVar("--dash-line", "rgba(30, 30, 30, 0.055)");



        if (targetY > plot.top) {

            chart.appendChild(svg("rect", {

                x: plot.left,

                y: plot.top,

                width: plot.right - plot.left,

                height: targetY - plot.top,

                rx: 6,

                fill:
                    isGoodRatio
                        ? green
                        : brand,

                "fill-opacity":
                    isGoodRatio
                        ? 0.045
                        : 0.03,

            }));

        }



        if (targetY < plot.bottom) {

            chart.appendChild(svg("rect", {

                x: plot.left,

                y: targetY,

                width: plot.right - plot.left,

                height: plot.bottom - targetY,

                fill:
                    isGoodRatio
                        ? brand
                        : green,

                "fill-opacity":
                    isGoodRatio
                        ? 0.03
                        : 0.045,

            }));

        }



        for (let value = axis.minimum; value <= axis.maximum + 0.0001; value += axis.step) {

            chart.appendChild(svg("line", {

                x1: plot.left,

                x2: plot.right,

                y1: yForValue(value),

                y2: yForValue(value),

                stroke: gridColour,

                "stroke-width": 1,

            }));

        }



        points.forEach((point, index) => {

            chart.appendChild(svg("line", {

                x1: xForIndex(index),

                x2: xForIndex(index),

                y1: plot.top,

                y2: plot.bottom,

                stroke: gridColour,

                "stroke-width": 1,

                "stroke-dasharray": "2 4",

            }));

        });



        addText(
            chart,
            isGoodRatio
                ? "Meets target"
                : "Above target",
            {

                x:
                    plot.left
                    + 10,

                y:
                    plot.top
                    + 14,

                "font-size":
                    9.5,

                fill:
                    isGoodRatio
                        ? green
                        : brand,

                "fill-opacity":
                    0.55,

            }
        );



        if (
            plot.bottom
            -
            targetY
            >
            22
        ) {

            addText(
                chart,
                isGoodRatio
                    ? "Below target"
                    : "Within target",
                {

                    x:
                        plot.left
                        + 10,

                    y:
                        plot.bottom
                        -
                        8,

                    "font-size":
                        9.5,

                    fill:
                        isGoodRatio
                            ? brand
                            : green,

                }
            );

        }





        /* Y-axis tick labels */



        for (let value = axis.minimum; value <= axis.maximum + 0.0001; value += axis.step) {

            addText(chart, `${Math.round(value)}%`, {

                x: plot.left - 6,

                y: yForValue(value) + 3,

                "text-anchor": "end",

                "font-size": 9,

            });

        }





        /* Axis titles */



        const midY = (plot.top + plot.bottom) / 2;



        addText(chart, metricLabel, {

            x: 10,

            y: midY,

            "text-anchor": "middle",

            transform: `rotate(-90 10 ${midY})`,

        }, "dashboard-chart-axis-title");



        addText(chart, "Date", {

            x: (plot.left + plot.right) / 2,

            y: height - 8,

            "text-anchor": "middle",

        }, "dashboard-chart-axis-title");





        /* Area + line */



        const coordinates = points.map((point, index) => ({

            x: xForIndex(index),

            y:
                yForValue(
                    metricValue(
                        point
                    )
                ),

        }));



        const linePath = coordinates

            .map((point, index) =>

                `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)

            .join(" ");



        const first = coordinates[0];

        const last = coordinates[coordinates.length - 1];



        const areaPath =

            `${linePath} L ${last.x.toFixed(2)} ${plot.bottom} ` +

            `L ${first.x.toFixed(2)} ${plot.bottom} Z`;



        const defs = svg("defs");

        const gradient = svg("linearGradient", {

            id: "dashboardTrendGradient",

            x1: 0,

            y1: 0,

            x2: 0,

            y2: 1,

        });



        gradient.appendChild(svg("stop", {

            offset: "0%",

            "stop-color": seriesColour,

            "stop-opacity": 0.3,

        }));



        gradient.appendChild(svg("stop", {

            offset: "100%",

            "stop-color": seriesColour,

            "stop-opacity": 0.03,

        }));



        defs.appendChild(gradient);

        chart.appendChild(defs);



        chart.appendChild(svg("path", {

            d: areaPath,

            fill: "url(#dashboardTrendGradient)",

            stroke: "none",

        }));





        /* Target line — full plot width */



        chart.appendChild(svg("line", {

            x1: plot.left,

            x2: plot.right,

            y1: targetY,

            y2: targetY,

            stroke: seriesColour,

            "stroke-width": 1.5,

            "stroke-dasharray": "5 4",

        }));



        chart.appendChild(svg("path", {

            d: linePath,

            fill: "none",

            stroke: seriesColour,

            "stroke-width": 2,

            "stroke-linecap": "round",

            "stroke-linejoin": "round",

        }));



        coordinates.forEach((coordinate, index) => {

            const isLast = index === coordinates.length - 1;

            chart.appendChild(svg("circle", {

                cx: coordinate.x,

                cy: coordinate.y,

                r: isLast ? 4.5 : 3,

                fill:
                    isLast
                        ? seriesColour
                        : cssVar(
                            "--dash-card",
                            "#FFFFFF"
                        ),

                stroke:
                    seriesColour,

                "stroke-width": isLast ? 2 : 1.6,

                "pointer-events": "none",

            }));

        });





        /* X labels */



        const maxLabels = Math.max(2, Math.floor((pointsRight - pointsLeft) / 52) + 1);

        const labelEvery = Math.max(1, Math.ceil(points.length / maxLabels));



        points.forEach((point, index) => {

            if (index % labelEvery !== 0 && index !== points.length - 1) {

                return;

            }

            addText(chart, point.label, {

                x: xForIndex(index),

                y: plot.bottom + 15,

                "text-anchor": "middle",

                "font-size": 9,

            });

        });





        /* Legend — one compact row above the plot, right aligned,

           laid out right-to-left: "— Bad Ratio   - - Target" */



        const legendY = 14;

        let legendCursor = plot.right;



        [

            {
                label:
                    "Target",
                dash:
                    "4 3",
                strokeWidth:
                    1.5
            },

            {
                label:
                    metricLabel,
                dash:
                    null,
                strokeWidth:
                    2
            },

        ].forEach((item) => {

            const text = addText(chart, item.label, {

                x: legendCursor,

                y: legendY + 4,

                "text-anchor": "end",

            }, "dashboard-chart-legend-text");



            let textWidth = 50;

            try {

                textWidth = text.getComputedTextLength();

            } catch (error) {

                /* keep fallback width */

            }



            const lineEnd = legendCursor - textWidth - 6;



            const line = svg("line", {

                x1: lineEnd - 16,

                x2: lineEnd,

                y1: legendY,

                y2: legendY,

                stroke: seriesColour,

                "stroke-width": item.strokeWidth,

            });



            if (item.dash) {

                line.setAttribute("stroke-dasharray", item.dash);

            }



            chart.appendChild(line);

            legendCursor = lineEnd - 16 - 18;

        });





        /* Last value label — above the last point */



        addText(chart, `${metricValue(points[points.length - 1]).toFixed(1)}%`, {

            x: Math.min(last.x, width - 24),

            y: last.y - 18,

            "text-anchor": "middle",

        }, "dashboard-chart-value");





        /* Hover */



        const guide = svg("line", {

            y1: plot.top,

            y2: plot.bottom,

            stroke: seriesColour,

            "stroke-opacity": 0.35,

            "stroke-width": 1,

            visibility: "hidden",

            "pointer-events": "none",

        });



        chart.appendChild(guide);



        const highlight = svg("circle", {

            r: 4,

            fill: seriesColour,

            stroke: cssVar("--dash-card", "#FFFFFF"),

            "stroke-width": 2,

            visibility: "hidden",

            "pointer-events": "none",

        });



        chart.appendChild(highlight);



        coordinates.forEach((coordinate, index) => {



            const point = points[index];



            /* Full-height hit column, easier to hover than a dot */

            const half = points.length > 1

                ? (pointsRight - pointsLeft) / (points.length - 1) / 2

                : 20;



            const hit = svg("rect", {

                x: coordinate.x - half,

                y: plot.top,

                width: half * 2,

                height: plot.bottom - plot.top,

                fill: "transparent",

                tabindex: 0,

            });



            const showTooltip = () => {

                guide.setAttribute("x1", coordinate.x);

                guide.setAttribute("x2", coordinate.x);

                guide.setAttribute("visibility", "visible");

                highlight.setAttribute("cx", coordinate.x);

                highlight.setAttribute("cy", coordinate.y);

                highlight.setAttribute("visibility", "visible");



                if (!chartTooltip) {

                    return;

                }



                chartTooltip.hidden = false;

                chartTooltip.innerHTML =

                    `<strong>${point.label}</strong>` +

                    `<br>${metricLabel}: <span style="color:${seriesColour};font-weight:700;">` +

                    `${metricValue(point).toFixed(1)}%</span>` +

                    `<br>Inspections: ${point.batches ?? "—"}` +

                    `<br>Products: ${integerFormat.format(num(point.judged))}`;



                const tipWidth = chartTooltip.offsetWidth || 130;



                chartTooltip.style.left =

                    `${Math.min(width - tipWidth, Math.max(0, coordinate.x - tipWidth / 2))}px`;



                chartTooltip.style.top =

                    `${Math.max(0, coordinate.y - (chartTooltip.offsetHeight || 64) - 12)}px`;

            };



            const hideTooltip = () => {

                guide.setAttribute("visibility", "hidden");

                highlight.setAttribute("visibility", "hidden");

                if (chartTooltip) {

                    chartTooltip.hidden = true;

                }

            };



            hit.addEventListener("mouseenter", showTooltip);

            hit.addEventListener("focus", showTooltip);

            hit.addEventListener("mouseleave", hideTooltip);

            hit.addEventListener("blur", hideTooltip);



            chart.appendChild(hit);

        });

    }





    trendMetricButtons.forEach((button) => {

        button.addEventListener("click", () => {

            const nextMetric =
                button.dataset.trendMetric;

            if (
                !nextMetric
                ||
                nextMetric === trendMetric
            ) {
                return;
            }

            trendMetric =
                nextMetric;

            trendMetricButtons.forEach((item) => {

                const active =
                    item.dataset.trendMetric
                    ===
                    trendMetric;

                item.classList.toggle(
                    "is-active",
                    active
                );

                item.setAttribute(
                    "aria-pressed",
                    active
                        ? "true"
                        : "false"
                );

            });

            drawChart();

        });

    });



    /* Redraw when the card resizes */



    if (chartWrap && "ResizeObserver" in window) {

        let frame = 0;

        new ResizeObserver(() => {

            cancelAnimationFrame(frame);

            frame = requestAnimationFrame(drawChart);

        }).observe(chartWrap);

    } else {

        window.addEventListener("resize", drawChart);

    }





    /* =====================================================

       ALIGN DATE PILL WITH THE THEME TOGGLE + BELL

       The toggle and bell live in base.html, so we measure them

       and place the pill one "gap" to their left, same centre line.

       ===================================================== */



    const filterWrap = page.querySelector(".dashboard-filter-wrap");

    const header = page.querySelector(".dashboard-header");



    function alignFilter() {



        if (!filterWrap || !header || !filterButton) {

            return;

        }



        filterWrap.style.top = "";

        filterWrap.style.right = "";

        filterButton.style.height = "";



        if (window.innerWidth < 1100) {

            return;

        }



        const headerRect = header.getBoundingClientRect();

        const pageRect = page.getBoundingClientRect();



        const controls = [...document.querySelectorAll(

            "button, a, [role='button'], label, input, iconsax-icon"

        )]

            .filter((element) => !page.contains(element))

            .map((element) => ({ element, rect: element.getBoundingClientRect() }))

            .filter(({ rect }) =>

                rect.width > 0 &&

                rect.height > 0 &&

                rect.width < 220 &&

                rect.top < headerRect.top + 90 &&

                rect.bottom > headerRect.top - 40 &&

                rect.left > pageRect.left + pageRect.width * 0.55

            )

            .sort((a, b) => a.rect.left - b.rect.left);



        if (!controls.length) {

            return;

        }



        /* Walk up to the visible pill that wraps the first control

           (e.g. the moon/sun toggle container). */

        let first = controls[0].element;

        let firstRect = controls[0].rect;



        while (first.parentElement && !first.parentElement.contains(page)) {

            const parentRect = first.parentElement.getBoundingClientRect();

            if (parentRect.width > 170 || parentRect.height > 70) {

                break;

            }

            first = first.parentElement;

            firstRect = parentRect;

        }



        const next = controls.find(({ rect }) => rect.left > firstRect.right + 2);

        const gap = next

            ? Math.min(28, Math.max(10, next.rect.left - firstRect.right))

            : 16;



        const height = Math.round(Math.min(44, Math.max(32, firstRect.height)));

        const centre = firstRect.top + firstRect.height / 2;



        filterButton.style.height = `${height}px`;

        filterWrap.style.right = `${Math.round(headerRect.right - firstRect.left + gap)}px`;

        filterWrap.style.top = `${Math.round(centre - headerRect.top - height / 2)}px`;

    }



    requestAnimationFrame(alignFilter);

    window.addEventListener("load", alignFilter);

    window.addEventListener("resize", alignFilter);

    document.fonts?.ready?.then(alignFilter);

    setTimeout(alignFilter, 400);





    /* =====================================================

       DATA LOADING / FILTER

       ===================================================== */



    async function loadDashboard(parameters) {



        page.classList.add("is-loading");



        try {

            const url = new URL(dashboardUrl, window.location.origin);



            Object.entries(parameters).forEach(([key, value]) => {

                if (value !== null && value !== undefined && value !== "") {

                    url.searchParams.set(key, value);

                }

            });



            const response = await fetch(url.toString(), {

                method: "GET",

                credentials: "same-origin",

                cache: "no-store",

            });



            const result = await response.json();



            if (!response.ok || !result.ok) {

                throw new Error(result.message || "Unable to load dashboard data.");

            }



            renderDashboard(result.dashboard);



            if (filterMenu) {

                filterMenu.hidden = true;

            }



            filterButton?.setAttribute("aria-expanded", "false");

        } catch (error) {

            console.error(error);

        } finally {

            page.classList.remove("is-loading");

        }

    }



    filterButton?.addEventListener("click", (event) => {

        event.stopPropagation();



        if (!filterMenu) {

            return;

        }



        filterMenu.hidden = !filterMenu.hidden;

        filterButton.setAttribute("aria-expanded", String(!filterMenu.hidden));

    });



    page.querySelectorAll("[data-dashboard-range]").forEach((button) => {

        button.addEventListener("click", () => {

            loadDashboard({ range: button.dataset.dashboardRange });

        });

    });



    customApply?.addEventListener("click", () => {

        loadDashboard({

            range: "custom",

            from: fromInput?.value,

            to: toInput?.value,

        });

    });



    document.addEventListener("click", (event) => {

        if (!filterMenu || filterMenu.hidden) {

            return;

        }



        if (filterMenu.contains(event.target) || filterButton?.contains(event.target)) {

            return;

        }



        filterMenu.hidden = true;

        filterButton?.setAttribute("aria-expanded", "false");

    });



    renderDashboard(dashboard);

});