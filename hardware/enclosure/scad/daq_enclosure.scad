// =====================================================================================
//  MIE1001 Team 5 DAQ enclosure  --  Arduino UNO R3 (SMD CH340 clone) + mie1001_daq_simple shield
//  Transparent PETG, 0.4 mm nozzle, no supports.  Two printed parts: BASE tray + LID.
//
//  Render one part:   openscad -D 'part="base"' -o ../stl/daq_base.stl daq_enclosure.scad
//                     openscad -D 'part="lid"'  -o ../stl/daq_lid.stl  daq_enclosure.scad
//  part = "assembly" | "exploded" | "base" | "lid" | "base_print" | "lid_print" | "report"
//
//  Frame (mm): origin = lower-left corner of the UNO seen from the top (USB-B and DC jacks on the
//  LEFT edge, power/analog header at the FRONT (y = 2.54), digital header at the BACK (y = 50.8)),
//  z = 0 on the table.  Connector positions of the shield come from pcb_positions.scad, which is
//  generated from the KiCad board by ../tools/make_positions.py -- do not type them in here.
// =====================================================================================
include <pcb_positions.scad>

part = "assembly";
$fn = 64;

// ---------------------------------------------------------------- print / fit
wall      = 2.4;     // side walls: 6 perimeters of 0.4 mm -> solid and clear
floor_t   = 2.4;     // base floor
lid_t     = 2.4;     // lid top plate
fit       = 0.3;     // PETG clearance on every sliding / plugging fit
chamfer   = 0.8;     // 45 deg chamfer on the bed edges (no elephant's foot, no overhang)
corner_r  = 3.0;     // vertical corner radius of the shell
label_d   = 0.6;     // text depth (engraved on the lid top, embossed on the walls)

// ---------------------------------------------------------------- the boards (measure yours!)
uno_l      = 68.58;  // UNO outline (A000066): 2.70 x 2.10 in
uno_w      = 53.34;
pcb_t      = 1.6;
standoff_h = 6.0;    // floor -> underside of the UNO (clears the UNO's through-hole solder tails)
jack_h     = 11.0;   // USB-B shell / DC jack height above the UNO top   [ASSUMED, measure the clone]
stack_gap  = 11.0;   // UNO top -> shield underside (shield rests on the USB-B shell, stacking hdr)
brk_h      = 14.5;   // highest point of a plugged breakout above the shield top
                     //   = 8.5 socket + 2.5 pin spacer + 1.6 PCB + ~1.9 parts / pin tips
hdr_h      = 8.5;    // stacking-header / socket bodies above the shield top
term_h     = 9.2;    // Phoenix PT 1,5/2-3,5-H body height (KiCad 3D model bbox)
wire_z_rel = 3.9;    // wire-entry centre above the shield top          [ASSUMED from Phoenix drawing]
sma_h      = 10.2;   // Amphenol 132134 height above the shield          [ASSUMED]
lid_clear  = 2.0;    // breakouts -> lid ceiling

// jacks of the UNO (A000066 board-outline drawing, scaled; clones vary +-0.5 mm)
usb_y = 38.1;  usb_w = 12.0;  usb_over = 6.5;  usb_in = 9.7;   // centre y, width, overhang, depth on board
dc_y  = 7.0;   dc_w  = 9.2;   dc_over  = 1.6;  dc_in  = 12.7;
dc_cz = 6.4;                                                    // DC plug axis above the UNO top

// UNO mounting holes (A000066).  Screws only in the two right-hand holes (= shield H2, H3): the stack
// is clamped there through a spacer between the boards.  The two left holes get support pins with a
// locating peg: at (13.97, 2.54) an M3 head / spacer would hit the DC jack body (the A000066 drawing
// shows the hole partly under it), at (15.24, 50.8) it would hit the SCL header pin.
uno_holes  = [[66.04, 7.62], [66.04, 35.56]];       // M3 heat-set inserts
uno_pegs   = [[13.97, 2.54], [15.24, 50.80]];       // support pin + peg
boss_d     = 7.0;
peg_boss_d = 5.0;
spacer_od  = 5.6;   // printed spacer between UNO and shield at H2/H3 (round: clears the ICSP header)
insert_d   = 4.0;               // M3 x 5.7 heat-set insert (CNC-Kitchen type) -> 4.0 mm hole
insert_len = 6.5;

// ---------------------------------------------------------------- derived heights
uno_z0     = floor_t + standoff_h;          // UNO underside
uno_top    = uno_z0 + pcb_t;
shield_z0  = uno_top + stack_gap;
shield_top = shield_z0 + pcb_t;
z_split    = uno_top + jack_h + 1.0;        // base / lid parting plane: 1 mm above both jacks
z_ceil     = shield_top + brk_h + lid_clear;
z_top      = z_ceil + lid_t;
wire_z     = shield_top + wire_z_rel;

// ---------------------------------------------------------------- cavity & shell
cx = 2.0;  cy = 1.5;                        // board edge -> inner wall (x: terminals overhang ~1 mm)
xi0 = -cx;  xi1 = uno_l + cx;  yi0 = -cy;  yi1 = uno_w + cy;
xo0 = xi0 - wall;  xo1 = xi1 + wall;  yo0 = yi0 - wall;  yo1 = yi1 + wall;

// lid screws: 4 x M3 x 30 countersunk (ISO 10642) from below, into heat-set inserts in the lid
post_r   = 4.0;
post_off = 2.0;                              // post centre diagonal offset outside the cavity corner
posts = [[xi0 - post_off, yi0 - post_off], [xi1 + post_off, yi0 - post_off],
         [xi0 - post_off, yi1 + post_off], [xi1 + post_off, yi1 + post_off]];
lid_insert_depth = 10.0;                     // 5.7 insert + room for the screw tip

// ---------------------------------------------------------------- openings
// USB-B and DC: U-notches in the base wall, open at the parting plane (the stack drops in from above)
usb_notch = [usb_y - usb_w/2 - 1.0, usb_y + usb_w/2 + 1.0, uno_top - 1.0];   // y0, y1, z bottom
dc_notch  = [dc_y  - dc_w/2 - 1.2,  dc_y  + dc_w/2 + 1.2,  uno_top - 1.0];
// Wire slots for the screw terminals, open at the bottom edge of the lid wall
sigtrig_slot = [J1_crtyd[1] - 0.8, J3_crtyd[3] + 0.8, wire_z + 2.5];          // y0, y1, z top
qps_slot     = [J2_crtyd[1] - 0.8, J2_crtyd[3] + 0.8, wire_z + 2.5];
// screwdriver windows in the lid top over the terminal screws (whole block top, front part)
sigtrig_win = [J1_crtyd[0] + 0.8, J1_crtyd[1] + 0.3, J1_pads[0][0] + 1.6, J3_crtyd[3] - 0.3];
qps_win     = [J2_pads[0][0] - 1.6, J2_crtyd[1] + 0.3, J2_crtyd[2] - 0.8, J2_crtyd[3] - 0.3];
// J4 header: slot for 4 Dupont plugs
j4_slot = [J4_pads[0][0] - 1.27 - 1.0, J4_pads[0][1] - 1.27 - 1.0,
           J4_pads[3][0] + 1.27 + 1.0, J4_pads[0][1] + 1.27 + 1.0];
// Faraday cup coax
faraday_mode = "passthrough";  // "passthrough": the SMA(m)->BNC(f) adapter goes up through the lid
                               // "bulkhead"   : BNC bulkhead jack in the lid + short SMA pigtail
faraday_pass_d = 12.5;         // clears the adapter's BNC bayonet studs (11.6) and SMA nut (9.2)
bnc_bulk_d = 9.7;  bnc_bulk_flat = 8.9;   // D-hole for a 3/8-32 BNC bulkhead jack [check its datasheet]
tie_slot = [4.6, 2.0];         // cable-tie slots (x, y) next to the BNC: tie the cable to the lid
// reset: the UNO's button is under the shield -> optional 7 mm hole for a panel push button
//        wired to RESET + GND of the stacking header (see README)
reset_button = true;
reset_pos = [8.0, 45.0];  reset_d = 7.0;
// copper-tape patch over the preamp (inside of the lid ceiling): engraved outline as a guide
patch = [26.0, 36.5, 63.0, 52.0];  // x0 y0 x1 y1, covers guard_bbox + VREF buffer + output filter
// ventilation: inlet slots low in the base (front+back), outlet slots high in the lid front wall
vent_x = [26, 30, 34, 38, 42];  vent_w = 1.8;

// ---------------------------------------------------------------- colours for the renders
c_petg = [0.75, 0.9, 1.0, 0.35];
c_petg_solid = [0.55, 0.78, 0.95, 1.0];

// =====================================================================================
//  helpers
// =====================================================================================
module rrect(x0, y0, x1, y1, r, h) {
    hull() for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r]) translate([x, y, 0]) cylinder(r = r, h = h);
}
// rounded box with a 45 deg chamfer at z = 0 (bottom) or z = h (top)
module cbox(x0, y0, x1, y1, r, h, bottom = true, top = false) {
    c = chamfer;
    hull() {
        translate([0, 0, bottom ? c : 0]) rrect(x0, y0, x1, y1, r, h - (bottom ? c : 0) - (top ? c : 0));
        if (bottom) rrect(x0 + c, y0 + c, x1 - c, y1 - c, r - c, c);
        if (top) translate([0, 0, h - c]) rrect(x0 + c, y0 + c, x1 - c, y1 - c, r - c, c);
    }
}
module ccyl(r, h, bottom = true, top = false) {
    c = chamfer;
    hull() {
        translate([0, 0, bottom ? c : 0]) cylinder(r = r, h = h - (bottom ? c : 0) - (top ? c : 0));
        if (bottom) cylinder(r = r - c, h = c);
        if (top) translate([0, 0, h - c]) cylinder(r = r - c, h = c);
    }
}
module box(x0, y0, z0, x1, y1, z1) translate([x0, y0, z0]) cube([x1 - x0, y1 - y0, z1 - z0]);
// text on a wall, reading correctly from outside. side: "L" (-x), "R" (+x), "F" (-y), "B" (+y)
module wall_text(t, side, u, z, size = 3.5, depth = label_d) {
    if (side == "L") translate([xo0 + 0.01, u, z]) rotate([90, 0, -90]) linear_extrude(depth) text(t, size, "Liberation Sans:style=Bold", halign = "center", valign = "center");
    if (side == "R") translate([xo1 - 0.01, u, z]) rotate([90, 0, 90]) linear_extrude(depth) text(t, size, "Liberation Sans:style=Bold", halign = "center", valign = "center");
    if (side == "F") translate([u, yo0 + 0.01, z]) rotate([90, 0, 0]) linear_extrude(depth) text(t, size, "Liberation Sans:style=Bold", halign = "center", valign = "center");
}
// engraved text in the lid top (the top is printed face-down, so raised text is impossible)
module top_text(t, x, y, size, rot = 0, halign = "center") {
    translate([x, y, z_top - label_d]) rotate(rot) linear_extrude(label_d + 0.1)
        text(t, size, "Liberation Sans:style=Bold", halign = halign, valign = "center");
}
// horizontal tunnel along y without overhang (diamond = two 45 deg roofs)
module diamond_y(x, z, y0, y1, w) translate([x, y0, z]) rotate([-90, 0, 0]) rotate(45) cube([w / sqrt(2), w / sqrt(2), y1 - y0]);

// =====================================================================================
//  BASE tray
// =====================================================================================
module base() {
    difference() {
        union() {
            difference() {
                cbox(xo0, yo0, xo1, yo1, corner_r, z_split);
                box(xi0, yi0, floor_t, xi1, yi1, z_split + 1);
            }
            for (p = posts) translate([p[0], p[1], 0]) cylinder(r = post_r, h = z_split);   // no bed chamfer: the countersink needs the full diameter
            // UNO bosses (heat-set inserts) and the support pin under the 4th hole
            for (h = uno_holes) translate([h[0], h[1], 0]) cylinder(d = boss_d, h = uno_z0);
            for (h = uno_pegs) translate([h[0], h[1], 0]) {
                cylinder(d = peg_boss_d, h = uno_z0);
                cylinder(d = 3.2 - 2 * fit, h = uno_z0 + pcb_t - 0.2);
                translate([0, 0, uno_z0 + pcb_t - 0.2]) cylinder(d1 = 3.2 - 2 * fit, d2 = 1.8, h = 0.6);
            }
            // cable-tie buttresses under the wire slots (outside the walls)
            tie_buttress("L", (sigtrig_slot[0] + sigtrig_slot[1]) / 2, sigtrig_slot[1] - sigtrig_slot[0] - 3);
            tie_buttress("R", (qps_slot[0] + qps_slot[1]) / 2, qps_slot[1] - qps_slot[0] - 1);
            wall_text("USB", "L", usb_y, uno_top - 4.0, 3.0);
            wall_text("DC 7-12V", "L", dc_y + 0.8, uno_top - 4.2, 2.2);
            wall_text("MIE1001 TEAM 5 DAQ", "F", uno_l / 2, 13.5, 3.2);
        }
        // jack notches
        box(xo0 - 1, usb_notch[0], usb_notch[2], xi0 + 0.1, usb_notch[1], z_split + 1);
        box(xo0 - 1, dc_notch[0], dc_notch[2], xi0 + 0.1, dc_notch[1], z_split + 1);
        // lid screw holes: 3.4 through + 90 deg countersink at the bottom (M3 ISO 10642, head 6.0)
        for (p = posts) translate([p[0], p[1], -0.1]) {
            cylinder(d = 3.4, h = z_split + 1);
            cylinder(d1 = 6.6, d2 = 3.4, h = 1.6);
        }
        // heat-set insert holes in the UNO bosses
        for (h = uno_holes) translate([h[0], h[1], uno_z0 - insert_len]) cylinder(d = insert_d, h = insert_len + 1);
        // inlet vents, low in the front and back walls (vertical slots: 1.8 mm bridge only)
        for (x = vent_x) {
            box(x - vent_w / 2, yo0 - 1, floor_t + 1.0, x + vent_w / 2, yi0 + 1, floor_t + 5.0);
            box(x + 4 - vent_w / 2, yi1 - 1, floor_t + 1.0, x + 4 + vent_w / 2, yo1 + 1, floor_t + 5.0);
        }
        // recesses for 4 self-adhesive rubber bumpers (10 mm x 1 mm deep, printable: opens on the bed)
        for (p = [[8, 7], [uno_l - 8, 7], [8, uno_w - 7], [uno_l - 8, uno_w - 7]])
            translate([p[0], p[1], -0.1]) cylinder(d = 10.5, h = 1.1);
    }
}
module tie_buttress(side, yc, len) {
    x_wall = side == "L" ? xo0 : xo1;
    s = side == "L" ? -1 : 1;
    top = wire_z - 1.8;                      // wires rest on it just below the slot
    difference() {
        union() {
            // below the parting plane it is welded to the base wall ...
            hull() {
                translate([side == "L" ? x_wall - 6 : x_wall - 0.01, yc - len / 2, 0]) cube([6.01, len, z_split - 0.01]);
            }
            // ... above it, it stands 0.3 mm off the wall so the lid wall slides past
            translate([side == "L" ? x_wall - 6 : x_wall + fit, yc - len / 2, 0]) cube([6 - fit, len, top]);
        }
        // tunnel for a cable tie (up to 4.8 mm wide), 45 deg roof
        diamond_y(x_wall + s * 3.4, top - 4.2, yc - len / 2 - 1, yc + len / 2 + 1, 4.2);
        // bed chamfer
        translate([x_wall + s * 6, yc - len / 2 - 1, 0]) rotate([0, 45, 0]) cube([chamfer * 1.42, len + 2, chamfer * 1.42], center = true);
    }
}

// =====================================================================================
//  LID  (modelled in place; printed upside-down, top face on the bed)
// =====================================================================================
module lid() {
    difference() {
        union() {
            difference() {
                translate([0, 0, z_split]) cbox(xo0, yo0, xo1, yo1, corner_r, z_top - z_split, bottom = false, top = true);
                box(xi0, yi0, z_split - 1, xi1, yi1, z_ceil);
            }
            for (p = posts) translate([p[0], p[1], z_split]) ccyl(post_r, z_top - z_split, bottom = false, top = true);
            wall_text("SIG", "L", (J1_crtyd[1] + J1_crtyd[3]) / 2, wire_z + 7.5, 2.8);
            wall_text("TRIG", "L", (J3_crtyd[1] + J3_crtyd[3]) / 2, wire_z + 7.5, 2.8);
            wall_text("QPS OUT", "R", (J2_crtyd[1] + J2_crtyd[3]) / 2, wire_z + 7.5, 2.8);
        }
        // wire slots for J1/J3 (left) and J2 (right): open at the lid's lower edge
        box(xo0 - 1, sigtrig_slot[0], z_split - 1, xi0 + 0.1, sigtrig_slot[1], sigtrig_slot[2]);
        box(xi1 - 0.1, qps_slot[0], z_split - 1, xo1 + 1, qps_slot[1], qps_slot[2]);
        // screwdriver windows over the terminal screws, J4 slot
        box(sigtrig_win[0], sigtrig_win[1], z_ceil - 1, sigtrig_win[2], sigtrig_win[3], z_top + 1);
        box(qps_win[0], qps_win[1], z_ceil - 1, qps_win[2], qps_win[3], z_top + 1);
        box(j4_slot[0], j4_slot[1], z_ceil - 1, j4_slot[2], j4_slot[3], z_top + 1);
        // Faraday cup coax
        translate([J5_pos[0], J5_pos[1], z_ceil - 1]) {
            if (faraday_mode == "passthrough") cylinder(d = faraday_pass_d, h = lid_t + 2);
            else intersection() {
                cylinder(d = bnc_bulk_d, h = lid_t + 2);
                translate([-bnc_bulk_d / 2, -bnc_bulk_d / 2, 0]) cube([bnc_bulk_flat, bnc_bulk_d, lid_t + 2]);
            }
        }
        for (dy = [-3.5, 3.5]) translate([J5_pos[0] + 9.3 - tie_slot[0] / 2, J5_pos[1] + dy - tie_slot[1] / 2, z_ceil - 1])
            cube([tie_slot[0], tie_slot[1], lid_t + 2]);
        if (reset_button) translate([reset_pos[0], reset_pos[1], z_ceil - 1]) cylinder(d = reset_d, h = lid_t + 2);
        // outlet vents high in the front wall
        for (x = vent_x) box(x + 2 - vent_w / 2, yo0 - 1, z_ceil - 7.0, x + 2 + vent_w / 2, yi0 + 1, z_ceil - 1.5);
        // heat-set inserts in the lid posts (from the parting plane)
        for (p = posts) translate([p[0], p[1], z_split - 0.1]) {
            cylinder(d = insert_d, h = 6.2);
            cylinder(d = 2.8, h = lid_insert_depth);
        }
        // engraved labels on the top
        top_text("MIE1001  TEAM 5  DAQ", 27, 5.0, 3.4);
        top_text("SIG", sigtrig_win[2] + 2.6, (J1_crtyd[1] + J1_crtyd[3]) / 2, 2.6, 90);
        top_text("TRIG", sigtrig_win[2] + 2.6, (J3_crtyd[1] + J3_crtyd[3]) / 2, 2.6, 90);
        top_text("QPS OUT", (qps_win[0] + qps_win[2]) / 2 - 1.5, qps_win[3] + 2.4, 2.4);
        top_text("PRE A2 VREF GND", j4_slot[0] - 0.5, j4_slot[1] - 2.2, 2.3, 0, "left");
        top_text("FARADAY CUP", J5_pos[0] - faraday_pass_d / 2 - 1.5, J5_pos[1] + 1.8, 3.0, 0, "right");
        top_text(faraday_mode == "passthrough" ? "SMA > BNC" : "BNC", J5_pos[0] - faraday_pass_d / 2 - 1.5, J5_pos[1] - 2.6, 2.4, 0, "right");
        if (reset_button) top_text("RESET", reset_pos[0], reset_pos[1] - reset_d / 2 - 2.6, 2.4);
        // copper-tape guide: 0.4 mm engraved outline on the underside of the lid top
        translate([0, 0, z_ceil - 0.01]) linear_extrude(0.41) difference() {
            translate([patch[0], patch[1]]) square([patch[2] - patch[0], patch[3] - patch[1]]);
            translate([patch[0] + 0.8, patch[1] + 0.8]) square([patch[2] - patch[0] - 1.6, patch[3] - patch[1] - 1.6]);
        }
    }
}

// =====================================================================================
//  placeholder boards for the renders
// =====================================================================================
uno_pts = [[0, 0], [66.04, 0], [66.04, 2.54], [68.58, 5.08], [68.58, 37.85], [66.04, 40.39],
           [66.04, 51.82], [64.52, 53.34], [0, 53.34]];
module stack() {
    // UNO
    color([0.0, 0.45, 0.55]) translate([0, 0, uno_z0]) linear_extrude(pcb_t) difference() {
        polygon(uno_pts); for (h = concat(uno_holes, uno_pegs)) translate(h) circle(d = 3.2);
    }
    color("silver") box(-usb_over, usb_y - usb_w / 2, uno_top, usb_in, usb_y + usb_w / 2, uno_top + jack_h - 0.1);
    color([0.15, 0.15, 0.15]) box(-dc_over, dc_y - dc_w / 2, uno_top, dc_in, dc_y + dc_w / 2, uno_top + jack_h);
    color([0.15, 0.15, 0.15]) {   // UNO headers (8.5 mm)
        box(17.5, 49.5, uno_top, 64.8, 52.1, uno_top + 8.5);
        box(26.7, 1.3, uno_top, 64.8, 3.8, uno_top + 8.5);
    }
    color("yellow") for (p = [[24.0, 42.5], [24.0, 39.5], [24.0, 36.5], [60.0, 27.0]]) translate([p[0], p[1], uno_top]) cube([1.6, 0.8, 0.6]);   // L TX RX ON (approx.)
    // stacking-header legs between the boards
    color("gold") for (x = [18.8 : 2.54 : 63.6]) translate([x, 50.8, uno_top + 8.5]) cylinder(d = 0.64, h = stack_gap - 8.5, $fn = 8);
    color("white") for (h = uno_holes) translate([h[0], h[1], uno_top]) spacer();
    // shield
    color([0.1, 0.5, 0.2]) translate([0, 0, shield_z0]) linear_extrude(pcb_t) difference() {
        polygon(uno_pts); for (h = pcb_holes) translate(h) circle(d = 3.2);
    }
    color([0.8, 0.5, 0.2, 0.9]) translate([0, 0, shield_top]) linear_extrude(0.05) translate([guard_bbox[0], guard_bbox[1]]) square([guard_bbox[2] - guard_bbox[0], guard_bbox[3] - guard_bbox[1]]);
    color([0.15, 0.15, 0.15]) {   // stacking-header bodies on the shield
        box(17.5, 49.5, shield_top, 64.8, 52.1, shield_top + hdr_h);
        box(26.7, 1.3, shield_top, 64.8, 3.8, shield_top + hdr_h);
    }
    color([0.1, 0.6, 0.25]) for (c = [J1_crtyd, J3_crtyd, J2_crtyd]) box(c[0] + 0.45, c[1] + 0.45, shield_top, c[2] - 0.45, c[3] - 0.45, shield_top + term_h);
    color([0.15, 0.15, 0.15]) {   // sockets U1, U2, J4
        box(U1_pads[0][0] - 1.27, U1_pads[0][1] - 1.27, shield_top, U1_pads[9][0] + 1.27, U1_pads[0][1] + 1.27, shield_top + hdr_h);
        box(U2_pads[0][0] - 1.27, U2_pads[5][1] - 1.27, shield_top, U2_pads[0][0] + 1.27, U2_pads[0][1] + 1.27, shield_top + hdr_h);
        box(J4_pads[0][0] - 1.27, J4_pads[0][1] - 1.27, shield_top, J4_pads[3][0] + 1.27, J4_pads[0][1] + 1.27, shield_top + hdr_h);
    }
    // breakouts lying flat on their pins
    color([0.1, 0.3, 0.8]) box(ads_outline[0], ads_outline[1], shield_top + 11, ads_outline[2], ads_outline[3], shield_top + 12.6);
    color([0.8, 0.1, 0.1]) box(mcp_outline[0], mcp_outline[1], shield_top + 11, mcp_outline[2], mcp_outline[3], shield_top + 12.6);
    color([0.2, 0.2, 0.2]) {
        box(24, 18, shield_top + 12.6, 28, 22, shield_top + brk_h - 0.4);
        box(51, 26, shield_top + 12.6, 55, 30, shield_top + brk_h - 0.4);
    }
    // SMA jack + SMA(m) -> BNC(f) adapter
    color("gold") translate([J5_pos[0] - 3.2, J5_pos[1] - 3.2, shield_top]) cube([6.4, 6.4, 1.6]);
    color("gold") translate([J5_pos[0], J5_pos[1], shield_top]) cylinder(d = 6.3, h = sma_h);
    color("silver") translate([J5_pos[0], J5_pos[1], shield_top + sma_h - 5]) {
        cylinder(d = 9.2, h = 8, $fn = 6);
        cylinder(d = 9.6, h = 31);
        translate([0, 0, 26]) rotate([90, 0, 0]) cylinder(d = 1.6, h = 11.6, center = true);
    }
}

// spacer between UNO and shield at H2/H3, for an M3 x 20 screw from the shield top into the insert
module spacer() difference() {
    cylinder(d = spacer_od, h = stack_gap - 0.2);
    translate([0, 0, -1]) cylinder(d = 3.4, h = stack_gap + 1);
}
module exploded() {
    color(c_petg) base();
    translate([0, 0, 22]) stack();
    translate([0, 0, 55]) color(c_petg) lid();
}

// =====================================================================================
//  numeric report (read by tools/fit_check.py)
// =====================================================================================
module report() {
    echo(str("R;z_split;", z_split)); echo(str("R;z_top;", z_top)); echo(str("R;z_ceil;", z_ceil));
    echo(str("R;uno_top;", uno_top)); echo(str("R;shield_top;", shield_top)); echo(str("R;wire_z;", wire_z));
    echo(str("R;xi;", [xi0, xi1])); echo(str("R;yi;", [yi0, yi1])); echo(str("R;xo;", [xo0, xo1])); echo(str("R;yo;", [yo0, yo1]));
    echo(str("R;posts;", posts)); echo(str("R;post_r;", post_r));
    echo(str("R;usb_notch;", usb_notch)); echo(str("R;dc_notch;", dc_notch));
    echo(str("R;sigtrig_slot;", sigtrig_slot)); echo(str("R;qps_slot;", qps_slot));
    echo(str("R;sigtrig_win;", sigtrig_win)); echo(str("R;qps_win;", qps_win)); echo(str("R;j4_slot;", j4_slot));
    echo(str("R;faraday_pass_d;", faraday_pass_d)); echo(str("R;reset;", [reset_pos[0], reset_pos[1], reset_d]));
    echo(str("R;usb;", [usb_y, usb_w, usb_over, jack_h])); echo(str("R;dc;", [dc_y, dc_w, dc_over, jack_h]));
    echo(str("R;uno_holes;", uno_holes)); echo(str("R;uno_pegs;", uno_pegs)); echo(str("R;spacer;", [spacer_od, stack_gap - 0.2])); echo(str("R;brk_top;", shield_top + brk_h));
    echo(str("R;term_top;", shield_top + term_h)); echo(str("R;hdr_top;", shield_top + hdr_h)); echo(str("R;patch;", patch));
}

// =====================================================================================
if (part == "base") base();
else if (part == "lid") lid();
else if (part == "base_print") base();
else if (part == "lid_print") translate([0, 0, z_top]) rotate([180, 0, 0]) lid();
else if (part == "exploded") exploded();
else if (part == "spacer") for (i = [0, 1]) translate([i * 9, 0, 0]) spacer();
else if (part == "report") { report(); cube(1); }
else if (part == "boards") stack();
else { color(c_petg) base(); stack(); color(c_petg) lid(); }
