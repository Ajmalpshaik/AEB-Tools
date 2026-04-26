# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Simple WPF options window for automatic plan dimensions.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-25
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : System.Windows.Markup, PresentationFramework, WindowsBase, PresentationCore
Input        : Active Revit document.
Output       : DimensionRequest instance or None when cancelled.
Notes        : UI is intentionally limited to production drafting choices only.
Changelog    : v1.0.0 - Cleaned and stabilised Auto Dimension workflow.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

import clr

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader

import collector
import constants
import models


_WINDOW_XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Auto Dimension"
    Width="500"
    Height="500"
    MinWidth="470"
    MinHeight="470"
    ResizeMode="CanResize"
    WindowStartupLocation="CenterScreen"
    ShowInTaskbar="False"
    Background="#FFF7F7F5">
    <Grid Margin="18">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="*" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
        </Grid.RowDefinitions>

        <Border Grid.Row="0" Padding="12" Background="#FFF1EFE6"
                BorderBrush="#FFD8D1B8" BorderThickness="1" CornerRadius="6">
            <StackPanel>
                <TextBlock FontSize="18" FontWeight="Bold" Foreground="#FF2F3B33"
                           Text="Auto Dimension" />
                <TextBlock Margin="0,4,0,0" TextWrapping="Wrap" Foreground="#FF49554E"
                           Text="Creates two room-side internal dimensions per room, plus external grid and overall wall-face dimensions in the active plan view." />
            </StackPanel>
        </Border>

        <Border Grid.Row="1" Margin="0,12,0,0" Padding="12"
                Background="#FFFFFFFF" BorderBrush="#FFD8D8D8"
                BorderThickness="1" CornerRadius="6">
            <StackPanel>
                <TextBlock FontWeight="SemiBold" Text="Create" Margin="0,0,0,6" />
                <CheckBox x:Name="internalRoomsCheckBox" Content="Internal room dimensions (width and length)" Margin="0,2,0,2" IsChecked="True" />
                <CheckBox x:Name="gridsCheckBox" Content="External grid dimensions" Margin="0,2,0,2" IsChecked="True" />
                <CheckBox x:Name="overallCheckBox" Content="Overall building dimension" Margin="0,2,0,2" IsChecked="True" />
            </StackPanel>
        </Border>

        <Border Grid.Row="2" Margin="0,10,0,0" Padding="12"
                Background="#FFFFFFFF" BorderBrush="#FFD8D8D8"
                BorderThickness="1" CornerRadius="6">
            <Grid>
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                </Grid.RowDefinitions>
                <TextBlock Grid.Row="0" FontWeight="SemiBold" Text="Offset distance (mm on paper)" Margin="0,0,0,6" />
                <TextBox Grid.Row="1" x:Name="offsetTextBox" Text="8" />
                <TextBlock Grid.Row="2" Margin="0,4,0,0" FontSize="11" Foreground="#FF7A7A7A"
                           Text="The model offset is multiplied by the active view scale." />
            </Grid>
        </Border>

        <Border Grid.Row="3" Margin="0,10,0,0" Padding="12"
                Background="#FFFFFFFF" BorderBrush="#FFD8D8D8"
                BorderThickness="1" CornerRadius="6">
            <StackPanel>
                <TextBlock FontWeight="SemiBold" Text="Dimension type" Margin="0,0,0,6" />
                <ComboBox x:Name="dimensionTypeComboBox" />
                <CheckBox x:Name="dryRunCheckBox" Margin="0,14,0,0"
                          Content="Preview only (dry run)" />
                <TextBlock x:Name="statusTextBlock" Margin="0,10,0,0" TextWrapping="Wrap"
                           Foreground="#FF6A5F43" />
            </StackPanel>
        </Border>

        <Grid Grid.Row="4" Margin="0,12,0,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*" />
                <ColumnDefinition Width="Auto" />
                <ColumnDefinition Width="Auto" />
            </Grid.ColumnDefinitions>
            <TextBlock Grid.Column="0" VerticalAlignment="Center" Foreground="#FF7A7467"
                       Text="Host model elements in active view" />
            <Button Grid.Column="1" x:Name="runButton" Width="120" Margin="0,0,8,0"
                    Content="Run" />
            <Button Grid.Column="2" x:Name="cancelButton" Width="100" IsCancel="True"
                    Content="Cancel" />
        </Grid>

        <Border Grid.Row="5" Margin="0,12,0,0" Padding="0,10,0,0"
                BorderBrush="#FFE2DED1" BorderThickness="0,1,0,0">
            <TextBlock HorizontalAlignment="Center" FontSize="11" Foreground="#FF7A7467"
                       TextAlignment="Center" TextWrapping="Wrap"
                       Text="All Rights Reserved (c) Ajmal P.S. | AJ Tools" />
        </Border>
    </Grid>
</Window>
"""


class _DimensionTypeOption(object):
    def __init__(self, dim_type_id, display_name):
        self.dim_type_id = dim_type_id
        self.display_name = display_name


def show_options_dialog(doc):
    window = XamlReader.Parse(_WINDOW_XAML)
    _populate_dimension_types(window, doc)

    state = {"request": None}
    run_button = window.FindName("runButton")
    cancel_button = window.FindName("cancelButton")

    def on_run_click(sender, args):  # pylint: disable=unused-argument
        offset = _read_offset(window)
        if offset is None:
            _set_status(window, "Enter a numeric offset between {0} and {1} mm.".format(
                constants.MIN_OFFSET_MM,
                constants.MAX_OFFSET_MM,
            ))
            return

        request = models.DimensionRequest(
            do_internal_rooms=bool(window.FindName("internalRoomsCheckBox").IsChecked),
            do_grids=bool(window.FindName("gridsCheckBox").IsChecked),
            do_overall=bool(window.FindName("overallCheckBox").IsChecked),
            offset_mm=offset,
            dimension_type_id=_selected_dim_type_id(window),
            dry_run=bool(window.FindName("dryRunCheckBox").IsChecked),
        )
        if not request.has_any_task():
            _set_status(window, "Tick at least one dimension option before running.")
            return

        state["request"] = request
        window.DialogResult = True
        window.Close()

    def on_cancel_click(sender, args):  # pylint: disable=unused-argument
        window.DialogResult = False
        window.Close()

    run_button.Click += on_run_click
    cancel_button.Click += on_cancel_click
    window.ShowDialog()
    return state["request"]


def _populate_dimension_types(window, doc):
    dim_types = collector.collect_linear_dimension_types(doc)
    options = [_DimensionTypeOption(None, "Default linear dimension type")]
    for dim_type in dim_types:
        try:
            display_name = dim_type.Name
        except Exception:
            display_name = "Linear"
        options.append(_DimensionTypeOption(dim_type.Id, display_name))
    combo = window.FindName("dimensionTypeComboBox")
    combo.ItemsSource = options
    combo.DisplayMemberPath = "display_name"
    combo.SelectedItem = options[0]


def _read_offset(window):
    text_value = window.FindName("offsetTextBox").Text
    try:
        offset = float(text_value)
    except Exception:
        return None
    if offset < constants.MIN_OFFSET_MM or offset > constants.MAX_OFFSET_MM:
        return None
    return offset


def _selected_dim_type_id(window):
    selected = window.FindName("dimensionTypeComboBox").SelectedItem
    if selected is None:
        return None
    return selected.dim_type_id


def _set_status(window, message):
    window.FindName("statusTextBlock").Text = message or ""
