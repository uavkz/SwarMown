import xlwt


def log_excel(
    name, # For file
    info, # Dict with fields - populations size, target weights, number of iterations, field, grid_step
    drones,  # Drones objects
    iterations, # Iterations - each target, overall, best
    best_reqs=None, # Best requirements for holes triangulation
):
    style_table_header = style("table_header")
    style_text = style("text")
    style_text_big = style("text_big")
    style_text_medium = style("text_medium")
    style_total = style("text_total")

    book = xlwt.Workbook()

    # INFO
    sheet_info = book.add_sheet("Info")
    sheet_info.portrait = False

    sheet_info.col(0).width = 256 * 40
    sheet_info.col(1).width = 256 * 40

    sheet_info.row(0).write(0, "Mission", style_text_big)
    sheet_info.row(0).write(1, info['mission'], style_text_big)
    sheet_info.row(1).write(0, "Field", style_text_big)
    sheet_info.row(1).write(1, info['field'], style_text_big)
    sheet_info.row(2).write(0, "Grid step (m)", style_text_big)
    sheet_info.row(2).write(1, info['grid_step'], style_text_big)
    sheet_info.row(3).write(0, "Population size", style_text_big)
    sheet_info.row(3).write(1, info['population_size'], style_text_big)
    sheet_info.row(4).write(0, "Number of iterations", style_text_big)
    sheet_info.row(4).write(1, info['number_of_iterations'], style_text_big)
    sheet_info.row(5).write(0, "Wage per start", style_text_big)
    sheet_info.row(5).write(1, info['start_price'], style_text_big)
    sheet_info.row(6).write(0, "Wage per hour", style_text_big)
    sheet_info.row(6).write(1, info['hourly_price'], style_text_big)
    sheet_info.row(7).write(0, "Boredline time", style_text_big)
    sheet_info.row(7).write(1, info['borderline_time'], style_text_big)
    sheet_info.row(8).write(0, "Max time", style_text_big)
    sheet_info.row(8).write(1, info['max_time'], style_text_big)
    sheet_info.row(9).write(0, "Max working speed", style_text_big)
    sheet_info.row(9).write(1, info['max_working_speed'], style_text_big)
    # Drones
    sheet_drones = book.add_sheet("Drones")
    sheet_drones.portrait = False

    sheet_drones.col(0).width = 256 * 11
    sheet_drones.col(1).width = 256 * 11
    sheet_drones.col(2).width = 256 * 11
    sheet_drones.col(3).width = 256 * 11
    sheet_drones.col(4).width = 256 * 11
    sheet_drones.col(5).width = 256 * 11
    sheet_drones.col(6).width = 256 * 15
    sheet_drones.col(7).width = 256 * 11
    sheet_drones.col(8).width = 256 * 11
    sheet_drones.col(9).width = 256 * 11

    sheet_drones.row(0).write(0, "Number", style_table_header)
    sheet_drones.row(0).write(1, "Id", style_table_header)
    sheet_drones.row(0).write(2, "Name", style_table_header)
    sheet_drones.row(0).write(3, "Max speed", style_table_header)
    sheet_drones.row(0).write(4, "Max distance", style_table_header)
    sheet_drones.row(0).write(5, "Slowdown ratio", style_table_header)
    sheet_drones.row(0).write(6, "Min slowdown ratio", style_table_header)
    sheet_drones.row(0).write(7, "Price per cycle", style_table_header)
    sheet_drones.row(0).write(8, "Price per kilometer", style_table_header)
    sheet_drones.row(0).write(9, "Price per hour", style_table_header)

    for i, drone in enumerate(drones):
        sheet_drones.row(i+1).write(0, i, style_text_medium)
        sheet_drones.row(i+1).write(1, drone.id, style_text_medium)
        sheet_drones.row(i+1).write(2, drone.name, style_text_medium)
        sheet_drones.row(i+1).write(3, drone.max_speed, style_text_medium)
        sheet_drones.row(i+1).write(4, drone.max_distance_no_load, style_text_medium)
        sheet_drones.row(i+1).write(5, drone.slowdown_ratio_per_degree, style_text_medium)
        sheet_drones.row(i+1).write(6, drone.min_slowdown_ratio, style_text_medium)
        sheet_drones.row(i+1).write(7, drone.price_per_cycle, style_text_medium)
        sheet_drones.row(i+1).write(8, drone.price_per_kilometer, style_text_medium)
        sheet_drones.row(i+1).write(9, drone.price_per_hour, style_text_medium)

    # Iterations
    sheet_iters = book.add_sheet("Iterations")
    sheet_iters.portrait = False

    sheet_iters.col(0).width = 256 * 11
    sheet_iters.col(1).width = 256 * 11
    sheet_iters.col(2).width = 256 * 11
    sheet_iters.col(3).width = 256 * 11
    sheet_iters.col(4).width = 256 * 11
    sheet_iters.col(5).width = 256 * 11
    sheet_iters.col(6).width = 256 * 11
    sheet_iters.col(7).width = 256 * 11
    sheet_iters.col(8).width = 256 * 11
    sheet_iters.col(9).width = 256 * 11
    sheet_iters.col(10).width = 256 * 11
    sheet_iters.col(11).width = 256 * 15
    sheet_iters.col(12).width = 256 * 15
    sheet_iters.col(13).width = 256 * 11
    sheet_iters.col(14).width = 256 * 11
    sheet_iters.col(15).width = 256 * 133

    sheet_iters.row(0).write(0, "Number", style_table_header)
    sheet_iters.row(0).write(1, "Best Distance", style_table_header)
    sheet_iters.row(0).write(2, "Average distance", style_table_header)
    sheet_iters.row(0).write(3, "Best time", style_table_header)
    sheet_iters.row(0).write(4, "Average time", style_table_header)
    sheet_iters.row(0).write(5, "Best drone price", style_table_header)
    sheet_iters.row(0).write(6, "Average drone price", style_table_header)
    sheet_iters.row(0).write(7, "Best salary", style_table_header)
    sheet_iters.row(0).write(8, "Average salary", style_table_header)
    sheet_iters.row(0).write(9, "Best penalty", style_table_header)
    sheet_iters.row(0).write(10, "Average penalty", style_table_header)
    sheet_iters.row(0).write(11, "Best number of starts", style_table_header)
    sheet_iters.row(0).write(12, "Average number of starts", style_table_header)
    sheet_iters.row(0).write(13, "Best fit", style_table_header)
    sheet_iters.row(0).write(14, "Average fit", style_table_header)
    sheet_iters.row(0).write(15, "Best solution", style_table_header)

    for i, iteration in enumerate(iterations):
        sheet_iters.row(i + 1).write(0, i, style_text_medium)
        sheet_iters.row(i + 1).write(1, iteration['best_distance'], style_text_medium)
        sheet_iters.row(i + 1).write(2, iteration['average_distance'], style_text_medium)
        sheet_iters.row(i + 1).write(3, iteration['best_time'], style_text_medium)
        sheet_iters.row(i + 1).write(4, iteration['average_time'], style_text_medium)
        sheet_iters.row(i + 1).write(5, iteration['best_drone_price'], style_text_medium)
        sheet_iters.row(i + 1).write(6, iteration['average_drone_price'], style_text_medium)
        sheet_iters.row(i + 1).write(7, iteration['best_salary'], style_text_medium)
        sheet_iters.row(i + 1).write(8, iteration['average_salary'], style_text_medium)
        sheet_iters.row(i + 1).write(9, iteration['best_penalty'], style_text_medium)
        sheet_iters.row(i + 1).write(10, iteration['average_penalty'], style_text_medium)
        sheet_iters.row(i + 1).write(11, iteration['best_number_of_starts'], style_text_medium)
        sheet_iters.row(i + 1).write(12, iteration['average_number_of_starts'], style_text_medium)
        sheet_iters.row(i + 1).write(13, iteration['best_fit'], style_text_medium)
        sheet_iters.row(i + 1).write(14, iteration['average_fit'], style_text_medium)
        if best_reqs:
            sheet_iters.row(i + 1).write(15, str(iteration['best_ind'] + [[r.area for r in best_reqs]]), style_text_medium)
        else:
            sheet_iters.row(i + 1).write(15, str(iteration['best_ind']), style_text_medium)

    book.save(f"{name}.xls")


def style(param):
    if param == "image":
        new_style = xlwt.XFStyle()
        new_style.borders.left = 0
    if param == "table_header":
        new_style = xlwt.XFStyle()
        new_style.alignment.wrap = 1
        new_style.font.bold = 1
        new_style.alignment.horz = xlwt.Alignment.HORZ_CENTER
        new_style.borders.top = 1
        new_style.borders.left = 1
        new_style.borders.right = 1
        new_style.borders.bottom = 1
        new_style.pattern.pattern = xlwt.Pattern.SOLID_PATTERN
        new_style.pattern.pattern_fore_colour = xlwt.Style.colour_map['gray25']
        return new_style
    if param == "text":
        new_style = xlwt.XFStyle()
        new_style.font.height = 8 * 22
        new_style.alignment.wrap = 1
        new_style.borders.top = 1
        new_style.borders.left = 1
        new_style.borders.right = 1
        new_style.borders.bottom = 1
        return new_style
    if param == "text_total":
        new_style = xlwt.XFStyle()
        new_style.font.height = 8 * 22
        new_style.alignment.wrap = 1
        new_style.font.bold = 1
        return new_style
    if param == "text_big":
        new_style = xlwt.XFStyle()
        new_style.font.height = 16 * 22
        new_style.alignment.horz = xlwt.Alignment.HORZ_CENTER
        return new_style
    if param == "text_medium":
        new_style = xlwt.XFStyle()
        new_style.font.height = 8 * 22
        new_style.alignment.horz = xlwt.Alignment.HORZ_CENTER
        return new_style
