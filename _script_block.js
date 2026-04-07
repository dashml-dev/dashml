
        function showPage(pageId, buttonElement) {
            // Hide all pages
            document.querySelectorAll('.page-content').forEach(page => {
                page.classList.remove('active');
            });

            // Remove active from all buttons
            document.querySelectorAll('.tab-button').forEach(btn => {
                btn.classList.remove('active');
            });

            // Show selected page
            document.getElementById('page-' + pageId).classList.add('active');
            buttonElement.classList.add('active');
        }

        // Geo country normalization
        const iso2ToTopo = {"AF":"Afghanistan", "AL":"Albania", "DZ":"Algeria", "AO":"Angola", "AR":"Argentina", "AM":"Armenia", "AU":"Australia", "AT":"Austria", "AZ":"Azerbaijan", "BS":"Bahamas", "BD":"Bangladesh", "BY":"Belarus", "BE":"Belgium", "BZ":"Belize", "BJ":"Benin", "BT":"Bhutan", "BO":"Bolivia", "BA":"Bosnia and Herz.", "BW":"Botswana", "BR":"Brazil", "BN":"Brunei", "BG":"Bulgaria", "BF":"Burkina Faso", "BI":"Burundi", "KH":"Cambodia", "CM":"Cameroon", "CA":"Canada", "CF":"Central African Rep.", "TD":"Chad", "CL":"Chile", "CN":"China", "CO":"Colombia", "CG":"Congo", "CR":"Costa Rica", "CI":"Côte d'Ivoire", "HR":"Croatia", "CU":"Cuba", "CY":"Cyprus", "CZ":"Czechia", "CD":"Dem. Rep. Congo", "DK":"Denmark", "DJ":"Djibouti", "DO":"Dominican Rep.", "EC":"Ecuador", "EG":"Egypt", "SV":"El Salvador", "GQ":"Eq. Guinea", "ER":"Eritrea", "EE":"Estonia", "SZ":"eSwatini", "ET":"Ethiopia", "FK":"Falkland Is.", "FJ":"Fiji", "FI":"Finland", "FR":"France", "GA":"Gabon", "GM":"Gambia", "GE":"Georgia", "DE":"Germany", "GH":"Ghana", "GR":"Greece", "GL":"Greenland", "GT":"Guatemala", "GN":"Guinea", "GW":"Guinea-Bissau", "GY":"Guyana", "HT":"Haiti", "HN":"Honduras", "HU":"Hungary", "IS":"Iceland", "IN":"India", "ID":"Indonesia", "IR":"Iran", "IQ":"Iraq", "IE":"Ireland", "IL":"Israel", "IT":"Italy", "JM":"Jamaica", "JP":"Japan", "JO":"Jordan", "KZ":"Kazakhstan", "KE":"Kenya", "KW":"Kuwait", "KG":"Kyrgyzstan", "LA":"Laos", "LV":"Latvia", "LB":"Lebanon", "LS":"Lesotho", "LR":"Liberia", "LY":"Libya", "LT":"Lithuania", "LU":"Luxembourg", "MK":"Macedonia", "MG":"Madagascar", "MW":"Malawi", "MY":"Malaysia", "ML":"Mali", "MR":"Mauritania", "MX":"Mexico", "MD":"Moldova", "MN":"Mongolia", "ME":"Montenegro", "MA":"Morocco", "MZ":"Mozambique", "MM":"Myanmar", "NA":"Namibia", "NP":"Nepal", "NL":"Netherlands", "NC":"New Caledonia", "NZ":"New Zealand", "NI":"Nicaragua", "NE":"Niger", "NG":"Nigeria", "KP":"North Korea", "NO":"Norway", "OM":"Oman", "PK":"Pakistan", "PS":"Palestine", "PA":"Panama", "PG":"Papua New Guinea", "PY":"Paraguay", "PE":"Peru", "PH":"Philippines", "PL":"Poland", "PT":"Portugal", "PR":"Puerto Rico", "QA":"Qatar", "RO":"Romania", "RU":"Russia", "RW":"Rwanda", "SA":"Saudi Arabia", "SN":"Senegal", "RS":"Serbia", "SL":"Sierra Leone", "SI":"Slovenia", "SB":"Solomon Is.", "SO":"Somalia", "ZA":"South Africa", "KR":"South Korea", "SS":"S. Sudan", "ES":"Spain", "LK":"Sri Lanka", "SD":"Sudan", "SR":"Suriname", "SE":"Sweden", "CH":"Switzerland", "SY":"Syria", "TW":"Taiwan", "TJ":"Tajikistan", "TZ":"Tanzania", "TH":"Thailand", "TL":"Timor-Leste", "TG":"Togo", "TT":"Trinidad and Tobago", "TN":"Tunisia", "TR":"Turkey", "TM":"Turkmenistan", "UG":"Uganda", "UA":"Ukraine", "AE":"United Arab Emirates", "GB":"United Kingdom", "US":"United States of America", "UY":"Uruguay", "UZ":"Uzbekistan", "VU":"Vanuatu", "VE":"Venezuela", "VN":"Vietnam", "EH":"W. Sahara", "YE":"Yemen", "ZM":"Zambia", "ZW":"Zimbabwe", "XK":"Kosovo"};
        const iso3ToTopo = {"AFG":"Afghanistan", "ALB":"Albania", "DZA":"Algeria", "AGO":"Angola", "ARG":"Argentina", "ARM":"Armenia", "AUS":"Australia", "AUT":"Austria", "AZE":"Azerbaijan", "BHS":"Bahamas", "BGD":"Bangladesh", "BLR":"Belarus", "BEL":"Belgium", "BLZ":"Belize", "BEN":"Benin", "BTN":"Bhutan", "BOL":"Bolivia", "BIH":"Bosnia and Herz.", "BWA":"Botswana", "BRA":"Brazil", "BRN":"Brunei", "BGR":"Bulgaria", "BFA":"Burkina Faso", "BDI":"Burundi", "KHM":"Cambodia", "CMR":"Cameroon", "CAN":"Canada", "CAF":"Central African Rep.", "TCD":"Chad", "CHL":"Chile", "CHN":"China", "COL":"Colombia", "COG":"Congo", "CRI":"Costa Rica", "CIV":"Côte d'Ivoire", "HRV":"Croatia", "CUB":"Cuba", "CYP":"Cyprus", "CZE":"Czechia", "COD":"Dem. Rep. Congo", "DNK":"Denmark", "DJI":"Djibouti", "DOM":"Dominican Rep.", "ECU":"Ecuador", "EGY":"Egypt", "SLV":"El Salvador", "GNQ":"Eq. Guinea", "ERI":"Eritrea", "EST":"Estonia", "SWZ":"eSwatini", "ETH":"Ethiopia", "FLK":"Falkland Is.", "FJI":"Fiji", "FIN":"Finland", "FRA":"France", "GAB":"Gabon", "GMB":"Gambia", "GEO":"Georgia", "DEU":"Germany", "GHA":"Ghana", "GRC":"Greece", "GRL":"Greenland", "GTM":"Guatemala", "GIN":"Guinea", "GNB":"Guinea-Bissau", "GUY":"Guyana", "HTI":"Haiti", "HND":"Honduras", "HUN":"Hungary", "ISL":"Iceland", "IND":"India", "IDN":"Indonesia", "IRN":"Iran", "IRQ":"Iraq", "IRL":"Ireland", "ISR":"Israel", "ITA":"Italy", "JAM":"Jamaica", "JPN":"Japan", "JOR":"Jordan", "KAZ":"Kazakhstan", "KEN":"Kenya", "KWT":"Kuwait", "KGZ":"Kyrgyzstan", "LAO":"Laos", "LVA":"Latvia", "LBN":"Lebanon", "LSO":"Lesotho", "LBR":"Liberia", "LBY":"Libya", "LTU":"Lithuania", "LUX":"Luxembourg", "MKD":"Macedonia", "MDG":"Madagascar", "MWI":"Malawi", "MYS":"Malaysia", "MLI":"Mali", "MRT":"Mauritania", "MEX":"Mexico", "MDA":"Moldova", "MNG":"Mongolia", "MNE":"Montenegro", "MAR":"Morocco", "MOZ":"Mozambique", "MMR":"Myanmar", "NAM":"Namibia", "NPL":"Nepal", "NLD":"Netherlands", "NCL":"New Caledonia", "NZL":"New Zealand", "NIC":"Nicaragua", "NER":"Niger", "NGA":"Nigeria", "PRK":"North Korea", "NOR":"Norway", "OMN":"Oman", "PAK":"Pakistan", "PSE":"Palestine", "PAN":"Panama", "PNG":"Papua New Guinea", "PRY":"Paraguay", "PER":"Peru", "PHL":"Philippines", "POL":"Poland", "PRT":"Portugal", "PRI":"Puerto Rico", "QAT":"Qatar", "ROU":"Romania", "RUS":"Russia", "RWA":"Rwanda", "SAU":"Saudi Arabia", "SEN":"Senegal", "SRB":"Serbia", "SLE":"Sierra Leone", "SVN":"Slovenia", "SLB":"Solomon Is.", "SOM":"Somalia", "ZAF":"South Africa", "KOR":"South Korea", "SSD":"S. Sudan", "ESP":"Spain", "LKA":"Sri Lanka", "SDN":"Sudan", "SUR":"Suriname", "SWE":"Sweden", "CHE":"Switzerland", "SYR":"Syria", "TWN":"Taiwan", "TJK":"Tajikistan", "TZA":"Tanzania", "THA":"Thailand", "TLS":"Timor-Leste", "TGO":"Togo", "TTO":"Trinidad and Tobago", "TUN":"Tunisia", "TUR":"Turkey", "TKM":"Turkmenistan", "UGA":"Uganda", "UKR":"Ukraine", "ARE":"United Arab Emirates", "GBR":"United Kingdom", "USA":"United States of America", "URY":"Uruguay", "UZB":"Uzbekistan", "VUT":"Vanuatu", "VEN":"Venezuela", "VNM":"Vietnam", "ESH":"W. Sahara", "YEM":"Yemen", "ZMB":"Zambia", "ZWE":"Zimbabwe", "XKX":"Kosovo"};
        const aliasToTopo = {"usa":"United States of America", "united states":"United States of America", "uk":"United Kingdom", "britain":"United Kingdom", "great britain":"United Kingdom", "england":"United Kingdom", "russian federation":"Russia", "republic of korea":"South Korea", "korea":"South Korea", "korea, republic of":"South Korea", "dprk":"North Korea", "korea, democratic people's republic of":"North Korea", "iran, islamic republic of":"Iran", "islamic republic of iran":"Iran", "syrian arab republic":"Syria", "viet nam":"Vietnam", "lao people's democratic republic":"Laos", "czech republic":"Czechia", "moldova, republic of":"Moldova", "republic of moldova":"Moldova", "taiwan, province of china":"Taiwan", "ivory coast":"Côte d'Ivoire", "cote d'ivoire":"Côte d'Ivoire", "burma":"Myanmar", "swaziland":"eSwatini", "the bahamas":"Bahamas", "north macedonia":"Macedonia", "uae":"United Arab Emirates", "bosnia and herzegovina":"Bosnia and Herz.", "bosnia":"Bosnia and Herz.", "democratic republic of the congo":"Dem. Rep. Congo", "drc":"Dem. Rep. Congo", "dr congo":"Dem. Rep. Congo", "republic of the congo":"Congo", "congo-brazzaville":"Congo", "dominican republic":"Dominican Rep.", "central african republic":"Central African Rep.", "equatorial guinea":"Eq. Guinea", "falkland islands":"Falkland Is.", "solomon islands":"Solomon Is.", "south sudan":"S. Sudan", "western sahara":"W. Sahara", "spain(canary is)":"Spain", "spain (canary is)":"Spain", "united kingdom":"United Kingdom", "venezuela, bolivarian republic of":"Venezuela", "bolivia, plurinational state of":"Bolivia", "tanzania, united republic of":"Tanzania", "united republic of tanzania":"Tanzania"};
        function detectGeoEncoding(values) {
            const sample = values.filter(v => v != null && v !== '').slice(0, 20);
            if (sample.every(v => /^[A-Z]{2}$/.test(String(v)))) return 'iso2';
            if (sample.every(v => /^[A-Z]{3}$/.test(String(v)))) return 'iso3';
            return 'name';
        }
        function normalizeCountryToTopo(value, encoding) {
            const v = String(value).trim();
            if (!v) return v;
            if (encoding === 'iso2') return iso2ToTopo[v.toUpperCase()] || v;
            if (encoding === 'iso3') return iso3ToTopo[v.toUpperCase()] || v;
            return aliasToTopo[v.toLowerCase()] || v;
        }
        function renderAllCharts() {
            // Metric: metric_total_funding
            {
              const filters = [];
              let d = applyFilters(dashmlData, filters);
              const vals = d.map(r => parseFloat(r['funding_amount'])).filter(v => !isNaN(v));
              const value = vals.length === 0 ? null :
                'sum' === 'sum' ? vals.reduce((a, b) => a + b, 0) :
                'sum' === 'mean' ? vals.reduce((a, b) => a + b, 0) / vals.length :
                vals.length;
              document.getElementById('chart-overview-metric_total_funding').textContent = formatMetric(value, ',.1f', 'M');
            }
            // Metric: metric_deal_count
            {
              const filters = [];
              let d = applyFilters(dashmlData, filters);
              const vals = d.map(r => parseFloat(r['funding_amount'])).filter(v => !isNaN(v));
              const value = vals.length === 0 ? null :
                'count' === 'sum' ? vals.reduce((a, b) => a + b, 0) :
                'count' === 'mean' ? vals.reduce((a, b) => a + b, 0) / vals.length :
                vals.length;
              document.getElementById('chart-overview-metric_deal_count').textContent = formatMetric(value, ',.0f', '');
            }
            // Metric: metric_avg_valuation
            {
              const filters = [];
              let d = applyFilters(dashmlData, filters);
              const vals = d.map(r => parseFloat(r['valuation'])).filter(v => !isNaN(v));
              const value = vals.length === 0 ? null :
                'mean' === 'sum' ? vals.reduce((a, b) => a + b, 0) :
                'mean' === 'mean' ? vals.reduce((a, b) => a + b, 0) / vals.length :
                vals.length;
              document.getElementById('chart-overview-metric_avg_valuation').textContent = formatMetric(value, ',.1f', 'M');
            }
            // Chart: line_funding_over_time
            const data_line_funding_over_time = (() => {
                const effectiveXType = getEffectiveType('funding_date', 'date');

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => d3.sum(v, d => d['funding_amount']),
                    d => d['funding_date']
                ).map(([funding_date, funding_amount]) => ({ funding_date, funding_amount }));

                // Sort
                
                if (effectiveXType === 'date') {
                    result.sort((a, b) => new Date(a.funding_date) - new Date(b.funding_date));
                } else if (effectiveXType === 'number') {
                    result.sort((a, b) => a.funding_date - b.funding_date);
                } else if (result.length > 0) {
                    const firstVal = result[0].funding_date;
                    if (firstVal instanceof Date) {
                        result.sort((a, b) => a.funding_date - b.funding_date);
                    } else if (typeof firstVal === 'number') {
                        result.sort((a, b) => a.funding_date - b.funding_date);
                    } else {
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.funding_date).localeCompare(String(b.funding_date)));
                    }
                }

                // Limit
                

                return result;
            })();
            const plot_line_funding_over_time = Plot.plot({
                marks: [
                    Plot.line(data_line_funding_over_time, {
                        x: "funding_date",
                        y: "funding_amount",
                        stroke: "#bd93f9",
                        strokeWidth: 2,
                        sort: "funding_date",
                        tip: true
                    }),
                    Plot.dot(data_line_funding_over_time, {
                        x: "funding_date",
                        y: "funding_amount",
                        fill: "#bd93f9",
                        r: 4
                    }),
                    Plot.ruleY([0])
                ],
                x: { type: "utc" },
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-overview-line_funding_over_time').appendChild(plot_line_funding_over_time);
            // Chart: area_deals_over_time
            const data_area_deals_over_time = (() => {
                const effectiveXType = getEffectiveType('funding_date', 'date');

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => v.length,
                    d => d['funding_date']
                ).map(([funding_date, funding_amount]) => ({ funding_date, funding_amount }));

                // Sort
                
                if (effectiveXType === 'date') {
                    result.sort((a, b) => new Date(a.funding_date) - new Date(b.funding_date));
                } else if (effectiveXType === 'number') {
                    result.sort((a, b) => a.funding_date - b.funding_date);
                } else if (result.length > 0) {
                    const firstVal = result[0].funding_date;
                    if (firstVal instanceof Date) {
                        result.sort((a, b) => a.funding_date - b.funding_date);
                    } else if (typeof firstVal === 'number') {
                        result.sort((a, b) => a.funding_date - b.funding_date);
                    } else {
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.funding_date).localeCompare(String(b.funding_date)));
                    }
                }

                // Limit
                

                return result;
            })();
            const plot_area_deals_over_time = Plot.plot({
                marks: [
                    Plot.areaY(data_area_deals_over_time, {
                        x: "funding_date",
                        y: "funding_amount",
                        fill: "#bd93f9",
                        fillOpacity: 0.7,
                        sort: "funding_date",
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                x: { type: "utc" },
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-overview-area_deals_over_time').appendChild(plot_area_deals_over_time);
            // D3 Pie Chart
            const data_pie_by_stage = (() => {
                const effectiveXType = getEffectiveType('stage', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => v.length,
                    d => d['stage']
                ).map(([stage, funding_amount]) => ({ stage, funding_amount }));

                // Sort
                
                if (effectiveXType === 'date') {
                    result.sort((a, b) => new Date(a.stage) - new Date(b.stage));
                } else if (effectiveXType === 'number') {
                    result.sort((a, b) => a.stage - b.stage);
                } else if (result.length > 0) {
                    const firstVal = result[0].stage;
                    if (firstVal instanceof Date) {
                        result.sort((a, b) => a.stage - b.stage);
                    } else if (typeof firstVal === 'number') {
                        result.sort((a, b) => a.stage - b.stage);
                    } else {
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.stage).localeCompare(String(b.stage)));
                    }
                }

                // Limit
                

                return result;
            })();
            const pieWidth = 400;
            const pieHeight = 400;
            const legendWidth = 150;
            const totalWidth = pieWidth + legendWidth;
            const radius = Math.min(pieWidth, pieHeight) / 2 - 10;

            const pie = d3.pie().value(d => d.funding_amount);
            const arc = d3.arc().innerRadius(0).outerRadius(radius);

            // Use theme secondary colors for categorical data
            const themeColors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c'];
            const color = d3.scaleOrdinal()
                .domain(data_pie_by_stage.map(d => d.stage))
                .range(themeColors);

            const svg = d3.create("svg")
                .attr("width", totalWidth)
                .attr("height", pieHeight)
                .attr("viewBox", [0, 0, totalWidth, pieHeight])
                .attr("style", "max-width: 100%; height: auto;");

            // Pie chart group (centered in left portion)
            const pieGroup = svg.append("g")
                .attr("transform", `translate(${pieWidth / 2}, ${pieHeight / 2})`);

            pieGroup.selectAll("path")
                .data(pie(data_pie_by_stage))
                .join("path")
                .attr("fill", d => color(d.data.stage))
                .attr("d", arc)
                .attr("stroke", "white")
                .attr("stroke-width", 2)
                .append("title")
                .text(d => `${d.data.stage}: ${d.data.funding_amount}`);

            // Legend (positioned on the right)
            const legend = svg.append("g")
                .attr("transform", `translate(${pieWidth + 10}, 20)`);

            data_pie_by_stage.forEach((d, i) => {
                const legendRow = legend.append("g")
                    .attr("transform", `translate(0, ${i * 25})`);

                legendRow.append("rect")
                    .attr("width", 15)
                    .attr("height", 15)
                    .attr("fill", color(d.stage))
                    .attr("rx", 2);

                legendRow.append("text")
                    .attr("x", 22)
                    .attr("y", 12)
                    .attr("fill", "#f8f8f2")
                    .style("font-size", "13px")
                    .text(d.stage);
            });

            document.getElementById('chart-overview-pie_by_stage').appendChild(svg.node());
            // Chart: bar_funding_by_industry
            const data_bar_funding_by_industry = (() => {
                const effectiveXType = getEffectiveType('industry', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => d3.sum(v, d => d['funding_amount']),
                    d => d['industry']
                ).map(([industry, funding_amount]) => ({ industry, funding_amount }));

                // Sort
                result.sort((a, b) => 1 * (a.funding_amount - b.funding_amount));

                // Limit
                

                return result;
            })();
            const plot_bar_funding_by_industry = Plot.plot({
                marks: [
                    Plot.barY(data_bar_funding_by_industry, {
                        x: "industry",
                        y: "funding_amount",
                        fill: "#bd93f9",
                        sort: null,
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                x: {
                    domain: data_bar_funding_by_industry.map(d => d.industry),
                    tickRotate: -45
                },
                marginLeft: 60,
                marginBottom: 100,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-by_industry-bar_funding_by_industry').appendChild(plot_bar_funding_by_industry);
            // Chart: stacked_bar_industry_stage
            const data_stacked_bar_industry_stage = (() => {
                const effectiveXType = getEffectiveType('industry', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => d3.sum(v, d => d['funding_amount']),
                    d => d['industry'],
                    d => d['stage']
                ).flatMap(([industryVal, groupData]) =>
                    groupData.map(([stageVal, funding_amountVal]) => ({
                        industry: industryVal,
                        stage: stageVal,
                        funding_amount: funding_amountVal
                    }))
                );

                // Sort
                result.sort((a, b) => 1 * (a.funding_amount - b.funding_amount));

                // Limit
                

                return result;
            })();
            const plot_stacked_bar_industry_stage = Plot.plot({
                marks: [
                    Plot.barY(data_stacked_bar_industry_stage, {
                        x: "industry",
                        y: "funding_amount",
                        fill: "stage",
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                x: {
                    domain: d3.groupSort(data_stacked_bar_industry_stage, g => d3.sum(g, d => d.funding_amount), d => d.industry)
                },
                color: {
                    domain: [...new Set(data_stacked_bar_industry_stage.map(d => d.stage))],
                    range: ["#50fa7b", "#ffb86c", "#ff5555", "#8be9fd", "#f1fa8c"]
                },
                marginLeft: 60,
                marginBottom: 100,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-by_industry-stacked_bar_industry_stage').appendChild(plot_stacked_bar_industry_stage);
            // Chart: grouped_bar_industry_stage
            const data_grouped_bar_industry_stage = (() => {
                const effectiveXType = getEffectiveType('industry', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => v.length,
                    d => d['industry'],
                    d => d['stage']
                ).flatMap(([industryVal, groupData]) =>
                    groupData.map(([stageVal, funding_amountVal]) => ({
                        industry: industryVal,
                        stage: stageVal,
                        funding_amount: funding_amountVal
                    }))
                );

                // Sort
                result.sort((a, b) => 1 * (a.funding_amount - b.funding_amount));

                // Limit
                

                return result;
            })();
            const plot_grouped_bar_industry_stage = Plot.plot({
                marks: [
                    Plot.barY(data_grouped_bar_industry_stage, {
                        fx: "industry",
                        x: "stage",
                        y: "funding_amount",
                        fill: "stage",
                        tip: true, sort: {x: "y"}
                    }),
                    Plot.ruleY([0])
                ],
                x: {
                    paddingInner: 0.1,
                    axis: null
                },
                fx: {
                    domain: d3.groupSort(data_grouped_bar_industry_stage, g => d3.sum(g, d => d.funding_amount), d => d.industry),
                    padding: 0.2
                },
                color: {
                    domain: [...new Set(data_grouped_bar_industry_stage.map(d => d.stage))],
                    range: ["#50fa7b", "#ffb86c", "#ff5555", "#8be9fd", "#f1fa8c"]
                },
                marginLeft: 60,
                marginBottom: 100,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-by_industry-grouped_bar_industry_stage').appendChild(plot_grouped_bar_industry_stage);
            // Chart: heatmap_industry_country
            const data_heatmap_industry_country = (() => {
                const effectiveXType = getEffectiveType('industry', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => d3.sum(v, d => d['funding_amount']),
                    d => d['industry'],
                    d => d['country']
                ).flatMap(([industryVal, groupData]) =>
                    groupData.map(([countryVal, funding_amountVal]) => ({
                        industry: industryVal,
                        country: countryVal,
                        funding_amount: funding_amountVal
                    }))
                );

                // Sort
                
                if (effectiveXType === 'date') {
                    result.sort((a, b) => new Date(a.industry) - new Date(b.industry));
                } else if (effectiveXType === 'number') {
                    result.sort((a, b) => a.industry - b.industry);
                } else if (result.length > 0) {
                    const firstVal = result[0].industry;
                    if (firstVal instanceof Date) {
                        result.sort((a, b) => a.industry - b.industry);
                    } else if (typeof firstVal === 'number') {
                        result.sort((a, b) => a.industry - b.industry);
                    } else {
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.industry).localeCompare(String(b.industry)));
                    }
                }

                // Limit
                

                return result;
            })();
            const plot_heatmap_industry_country = Plot.plot({
                marks: [
                    Plot.cell(data_heatmap_industry_country, {
                        x: "industry",
                        y: "country",
                        fill: "funding_amount",
                        tip: true
                    })
                ],
                color: {
                    type: "linear",
                    scheme: "purples",
                    legend: true,
                    label: "funding_amount"
                },
                marginLeft: 60,
                marginBottom: 100,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-by_industry-heatmap_industry_country').appendChild(plot_heatmap_industry_country);
            // Chart: geo_funding_by_country
            const data_geo_funding_by_country = (() => {
                const effectiveXType = getEffectiveType('country', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => d3.sum(v, d => d['funding_amount']),
                    d => d['country']
                ).map(([country, funding_amount]) => ({ country, funding_amount }));

                // Sort
                
                if (effectiveXType === 'date') {
                    result.sort((a, b) => new Date(a.country) - new Date(b.country));
                } else if (effectiveXType === 'number') {
                    result.sort((a, b) => a.country - b.country);
                } else if (result.length > 0) {
                    const firstVal = result[0].country;
                    if (firstVal instanceof Date) {
                        result.sort((a, b) => a.country - b.country);
                    } else if (typeof firstVal === 'number') {
                        result.sort((a, b) => a.country - b.country);
                    } else {
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.country).localeCompare(String(b.country)));
                    }
                }

                // Limit
                

                return result;
            })();
            const plot_geo_funding_by_country = Plot.plot({
                marks: (() => {
                    const enc = "name" || detectGeoEncoding(data_geo_funding_by_country.map(d => d.country));
                    const geoLookup = new Map(data_geo_funding_by_country.map(d => [normalizeCountryToTopo(d.country, enc).toLowerCase(), d.funding_amount]));
                    return [Plot.geo(window.worldTopojson, {
                        fill: d => {
                            const topoName = d.properties ? d.properties.name : null;
                            if (!topoName) return null;
                            return geoLookup.get(topoName.toLowerCase()) ?? null;
                        },
                        stroke: "#ccc",
                        strokeWidth: 0.5,
                        tip: true
                    })];
                })(),
                projection: "equal-earth",
                color: {
                    type: "linear",
                    scheme: "purples",
                    unknown: "#f0f0f0",
                    legend: true,
                    label: "funding_amount"
                },
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-geography-geo_funding_by_country').appendChild(plot_geo_funding_by_country);
            // Chart: bar_top_countries
            const data_bar_top_countries = (() => {
                const effectiveXType = getEffectiveType('country', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => d3.sum(v, d => d['funding_amount']),
                    d => d['country']
                ).map(([country, funding_amount]) => ({ country, funding_amount }));

                // Sort
                result.sort((a, b) => -1 * (a.funding_amount - b.funding_amount));

                // Limit
                result = result.slice(0, 10);

                return result;
            })();
            const plot_bar_top_countries = Plot.plot({
                marks: [
                    Plot.barY(data_bar_top_countries, {
                        x: "country",
                        y: "funding_amount",
                        fill: "#bd93f9",
                        sort: null,
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                x: {
                    domain: data_bar_top_countries.map(d => d.country),
                    tickRotate: -45
                },
                marginLeft: 60,
                marginBottom: 100,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-geography-bar_top_countries').appendChild(plot_bar_top_countries);
            // Chart: bar_top_cities
            const data_bar_top_cities = (() => {
                const effectiveXType = getEffectiveType('city', undefined);

                // Filter data
                let filteredData = dashmlData.filter(d => true);

                // Cast y values if y_type specified
                

                let result = d3.rollups(
                    filteredData,
                    v => v.length,
                    d => d['city']
                ).map(([city, count]) => ({ city, count }));

                // Sort
                result.sort((a, b) => -1 * (a.count - b.count));

                // Limit
                result = result.slice(0, 10);

                return result;
            })();
            const plot_bar_top_cities = Plot.plot({
                marks: [
                    Plot.barY(data_bar_top_cities, {
                        x: "city",
                        y: "count",
                        fill: "#bd93f9",
                        sort: null,
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                x: {
                    domain: data_bar_top_cities.map(d => d.city),
                    tickRotate: -45
                },
                marginLeft: 60,
                marginBottom: 100,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-geography-bar_top_cities').appendChild(plot_bar_top_cities);
            // Chart: scatter_funding_vs_valuation
            const data_scatter_funding_vs_valuation = dashmlData;
            const plot_scatter_funding_vs_valuation = Plot.plot({
                marks: [
                    Plot.dot(data_scatter_funding_vs_valuation, {
                        x: "funding_amount",
                        y: "valuation",
                        fill: "#bd93f9",
                        r: 5,
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-deep_dive-scatter_funding_vs_valuation').appendChild(plot_scatter_funding_vs_valuation);
            // Chart: histogram_funding
            const data_histogram_funding = dashmlData;
            const plot_histogram_funding = Plot.plot({
                marks: [
                    Plot.rectY(data_histogram_funding, Plot.binX({y: "count", thresholds: 30}, {
                        x: "funding_amount",
                        fill: "#bd93f9",
                        tip: true
                    })),
                    Plot.ruleY([0])
                ],
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-deep_dive-histogram_funding').appendChild(plot_histogram_funding);
            // Chart: box_funding_by_stage
            const data_box_funding_by_stage = dashmlData;
            const plot_box_funding_by_stage = Plot.plot({
                marks: [
                    Plot.boxY(data_box_funding_by_stage, {
                        x: "stage",
                        y: "funding_amount",
                        fill: "#bd93f9",
                        tip: true
                    }),
                    Plot.ruleY([0])
                ],
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-deep_dive-box_funding_by_stage').appendChild(plot_box_funding_by_stage);
            // Chart: bubble_industry
            const data_bubble_industry = (() => {
                // Filter data
                let filteredData = dashmlData.filter(d => true);

                let result = d3.rollups(
                    filteredData,
                    v => ({ funding_amount: d3.mean(v, d => d['funding_amount']), valuation: d3.mean(v, d => d['valuation']), employees: d3.mean(v, d => d['employees']) }),
                    d => d['industry']
                ).map(([industry, vals]) => ({ industry, funding_amount: vals.funding_amount, valuation: vals.valuation, employees: vals.employees }));

                // Sort
                result.sort((a, b) => 1 * (a.funding_amount - b.funding_amount));

                // Limit
                

                return result;
            })();
            const plot_bubble_industry = Plot.plot({
                marks: [
                    Plot.dot(data_bubble_industry, {
                        x: "funding_amount",
                        y: "valuation",
                        fill: "industry",
                        r: d => {
                            const maxVal = d3.max(data_bubble_industry, d => Math.abs(d["employees"]));
                            return 5 + (Math.abs(d["employees"]) / maxVal) * 25;
                        },
                        tip: true
                    }),
                    Plot.text(data_bubble_industry, {
                        x: "funding_amount",
                        y: "valuation",
                        text: "industry",
                        dy: -12,
                        fontSize: 10
                    }),
                    Plot.ruleY([0])
                ],
                color: {
                    domain: [...new Set(data_bubble_industry.map(d => d.industry))],
                    range: ["#50fa7b", "#ffb86c", "#ff5555", "#8be9fd", "#f1fa8c"]
                },
                marginLeft: 60,
                marginBottom: 40,
                grid: true,
                style: {
                    background: "transparent",
                    color: "#f8f8f2"
                }
            });
            document.getElementById('chart-deep_dive-bubble_industry').appendChild(plot_bubble_industry);
        }
    