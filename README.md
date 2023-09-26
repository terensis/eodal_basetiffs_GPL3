# EOdal data viewer
This project aims to provide a simple data viewer for EOdal. 
- Currently, the [[basis_script.py]] extracts S2 data for a specified AOI and writes it as TIFF files
- these TIFFs can then be visualized in a jupyter NB running folium (more advanced) or ipyleaflet (see corresponding jpynb files)

## TODO: 
- [ ] Make `nan` values transparent in folium
- [ ] Add all S2 tiffs to the folium map and allow selection from the map (via slider, dropdown, etc.)
- [ ] If desired: Make everything run in memory instead of writing out tiffs. THis has pros and cons...
- [ ] Accept user input to draw an AOI on the map (is this neccessary?)
- [ ] Integrate polygons (using geopandas) for quick visualization